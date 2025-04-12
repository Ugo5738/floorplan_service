# floorplan/management/commands/restore_floorplan_data.py
import hashlib
import logging
from collections import defaultdict
from datetime import datetime

from django.core.management.base import BaseCommand
from django.db import IntegrityError, connections, transaction
from django.utils import timezone

# Import NEW models from your app
from floorplan.models import (  # Use new names
    AllFloorsCsvData,
    AllFloorsData,
    CsvFloor,
    CsvRoom,
    CsvRoomDimensions,
    CsvRoomPixelData,
    CsvRoomScalingFactors,
    FloorPlan,
    FloorPlanAnalysisResult,
    PlanFloor,
    TotalAreasCsvData,
)

logger = logging.getLogger(__name__)

# --- Define OLD table names used in the backup ---
OLD_FP_ANALYSIS_TABLE = "floorplan_floorplananalysisresult"
OLD_FP_TABLE = "floorplan_floorplan"
OLD_AFD_TABLE = "floorplan_allfloorsdata"
OLD_PF_TABLE = "floorplan_planfloor"
OLD_CSVFLOOR_TABLE = "floorplan_csvfloor"
OLD_CSVROOM_TABLE = "floorplan_csvroom"
OLD_CSVROOMPIXEL_TABLE = "floorplan_csvroompixeldata"
OLD_CSVROOMDIM_TABLE = "floorplan_csvroomdimensions"
OLD_CSVROOMSCALE_TABLE = "floorplan_csvroomscalingfactors"
OLD_RAWROW_TABLE = "floorplan_allfloorscsvrawrow"
OLD_TOTALAREA_TABLE = "floorplan_totalareadata"


# --- Hashing function (matching the one in models.py) ---
def generate_new_hash_id(property_id, user_id, url):
    """Generates SHA-256 hash for prop_id|user_id|url combination."""
    if not all([property_id, user_id, url]):
        logger.debug(
            f"Cannot generate hash: Missing component for Prop:'{property_id}', User:'{user_id}', URL:'{url}'"
        )
        return None
    try:
        str_prop_id = str(property_id).strip()
        str_user_id = str(user_id).strip()
        str_url = str(url).strip()
        if not all([str_prop_id, str_user_id, str_url]):
            logger.debug(
                f"Cannot generate hash: Empty component after strip for Prop:'{property_id}', User:'{user_id}', URL:'{url}'"
            )
            return None
        combined_string = f"{str_prop_id}|{str_user_id}|{str_url}"
        string_bytes = combined_string.encode("utf-8")
        return hashlib.sha256(string_bytes).hexdigest()
    except Exception as e:
        logger.error(
            f"Error generating combined hash for '{property_id}|{user_id}|{url}': {e}"
        )
        return None


# --- User IDs to Exclude ---
EXCLUDED_USER_IDS = {"supersami54567", "supersami5456"}


class Command(BaseCommand):
    help = "Restores floorplan data from temporary DB backup, maps user IDs, excludes specific users, ensures unique FloorPlan hashes, and uses parent timestamps."

    def add_arguments(self, parser):
        parser.add_argument(
            "--temp-db-alias",
            type=str,
            default="temp_restore",
            help="Alias of the temporary restore database configured in settings.py",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=200,
            help="Number of records to process in each batch.",
        )
        parser.add_argument(
            "--clear-existing",
            action="store_true",
            help="DANGEROUS: Delete existing data from target floorplan tables before loading.",
        )

    def handle(self, *args, **options):
        temp_db = options["temp_db_alias"]
        batch_size = options["batch_size"]
        clear_existing = options["clear_existing"]
        prod_db = "default"

        self.stdout.write(f"Starting data restore from DB '{temp_db}' to '{prod_db}'.")
        self.stdout.write(
            f"Excluding records associated with old User IDs: {EXCLUDED_USER_IDS}"
        )
        self.stdout.write(
            self.style.WARNING(
                "Ensuring loaded FloorPlan records have unique hashes (based on PropID+UserID+URL)..."
            )
        )
        self.stdout.write(
            self.style.WARNING(
                "Using FloorPlanAnalysisResult.created_at for related records' timestamps where possible."
            )
        )
        if clear_existing:
            self.stdout.write(
                self.style.WARNING(
                    "Existing data in target floorplan tables WILL BE DELETED first."
                )
            )

        confirmation = input("Are you sure you want to proceed? (yes/no): ")
        if confirmation.lower() != "yes":
            self.stdout.write("Restore aborted by user.")
            return

        if clear_existing:
            self.clear_data(prod_db)

        try:
            # Run the main processing within a single transaction for consistency
            with transaction.atomic(using=prod_db):
                self.stdout.write("Processing data within a transaction...")

                # --- Process data model by model, passing PK maps and timestamps ---
                old_pk_maps = {}  # Store all old_pk -> new_pk maps
                analysis_creation_times = {}  # Store old_analysis_pk -> created_at

                old_pk_maps["analysis"], analysis_creation_times = (
                    self.migrate_analysis_results(temp_db, prod_db, batch_size)
                )
                old_pk_maps["floorplan"] = self.migrate_floorplans(
                    temp_db,
                    prod_db,
                    batch_size,
                    old_pk_maps["analysis"],
                    analysis_creation_times,
                )
                old_pk_maps["allfloorsdata"] = self.migrate_allfloorsdata(
                    temp_db,
                    prod_db,
                    batch_size,
                    old_pk_maps["floorplan"],
                    analysis_creation_times,
                )

                # Models needing FloorPlan PK Map
                self.migrate_planfloors(
                    temp_db,
                    prod_db,
                    batch_size,
                    old_pk_maps["floorplan"],
                    analysis_creation_times,
                )

                # Models needing AllFloorsData PK Map
                old_pk_maps["csvfloor"] = self.migrate_csvfloors(
                    temp_db,
                    prod_db,
                    batch_size,
                    old_pk_maps["allfloorsdata"],
                    analysis_creation_times,
                )
                self.migrate_rawrows(
                    temp_db,
                    prod_db,
                    batch_size,
                    old_pk_maps["allfloorsdata"],
                    analysis_creation_times,
                )
                self.migrate_totalareas(
                    temp_db,
                    prod_db,
                    batch_size,
                    old_pk_maps["allfloorsdata"],
                    analysis_creation_times,
                )

                # Models needing CsvFloor PK Map
                old_pk_maps["csvroom"] = self.migrate_csvrooms(
                    temp_db,
                    prod_db,
                    batch_size,
                    old_pk_maps["csvfloor"],
                    analysis_creation_times,
                )

                # Models needing CsvRoom PK Map
                self.migrate_csvroom_details(
                    temp_db,
                    prod_db,
                    batch_size,
                    old_pk_maps["csvroom"],
                    analysis_creation_times,
                )

            self.stdout.write(
                self.style.SUCCESS("Data restore transaction committed successfully.")
            )

        except Exception as e:
            logger.exception(
                "Error during data restore process. Transaction rolled back."
            )
            self.stderr.write(self.style.ERROR(f"Restore failed: {e}"))

    # --- Helper Functions ---

    def _get_cursor(self, db_alias):
        return connections[db_alias].cursor()

    def _execute_query(self, cursor, query):
        logger.debug(f"Executing query: {query[:200]}...")
        cursor.execute(query)
        return cursor

    def _get_parent_timestamp(
        self, target_model_name, fk_value, parent_model, pk_map, time_map, fallback_ts
    ):
        """Helper to find the timestamp by tracing back FKs."""
        parent_pk = pk_map.get(fk_value)
        if parent_pk:
            # Try getting timestamp directly if it's the AnalysisResult map
            if parent_model == FloorPlanAnalysisResult:
                return time_map.get(
                    fk_value, fallback_ts
                )  # Use old FK value for time map
            # Otherwise, query the parent object (assuming it exists now)
            try:
                # Select only the necessary field for timestamp propagation
                parent_obj = (
                    parent_model.objects.using("default")
                    .only("analysis_result__created_at")
                    .get(pk=parent_pk)
                )
                # Navigate relationships - adjust based on actual FK paths
                if isinstance(parent_obj, FloorPlan):
                    return parent_obj.analysis_result.created_at
                elif isinstance(parent_obj, AllFloorsData):
                    return parent_obj.floor_plan.analysis_result.created_at
                elif isinstance(parent_obj, CsvFloor):
                    return (
                        parent_obj.all_floors_data.floor_plan.analysis_result.created_at
                    )
                elif isinstance(parent_obj, CsvRoom):
                    return (
                        parent_obj.floor.all_floors_data.floor_plan.analysis_result.created_at
                    )
                # Add more cases if needed
            except Exception as e:
                logger.warning(
                    f"Could not retrieve timestamp for {target_model_name} via parent {parent_model.__name__} pk={parent_pk}: {e}"
                )
        return fallback_ts

    def clear_data(self, prod_db):
        """Deletes data from target tables in the production DB."""
        self.stdout.write("Clearing existing floorplan data...")
        models_to_clear = [
            TotalAreasCsvData,
            AllFloorsCsvData,
            CsvRoomPixelData,
            CsvRoomDimensions,
            CsvRoomScalingFactors,
            CsvRoom,
            CsvFloor,
            PlanFloor,
            AllFloorsData,
            FloorPlan,
            FloorPlanAnalysisResult,
        ]
        with transaction.atomic(using=prod_db):
            for model in models_to_clear:
                count, _ = model.objects.using(prod_db).all().delete()
                self.stdout.write(f"  Deleted {count} records from {model.__name__}")
        self.stdout.write("Existing data cleared.")

    def migrate_analysis_results(self, temp_db, prod_db, batch_size):
        """Migrates FloorPlanAnalysisResult, handling user mapping/exclusions and returning PK map and timestamp map."""
        self.stdout.write("Migrating FloorPlanAnalysisResult...")
        old_to_new_pk_map = {}
        analysis_creation_times = {}  # Store old_pk -> created_at
        total_processed = 0
        skipped_excluded = 0
        skipped_empty = 0
        ignored_dups = 0
        cursor = self._get_cursor(temp_db)
        self._execute_query(
            cursor,
            f"SELECT id, message, user_id, property_id, created_at FROM {OLD_FP_ANALYSIS_TABLE} ORDER BY id",
        )

        while True:
            old_rows = cursor.fetchmany(batch_size)
            if not old_rows:
                break
            new_objs_to_create = []
            temp_map = {}

            for row in old_rows:
                old_pk, message, user_id_orig, prop_id_orig, created_at_old = row
                if user_id_orig in EXCLUDED_USER_IDS:
                    skipped_excluded += 1
                    continue

                user_id, prop_id = user_id_orig, prop_id_orig
                if user_id == "447841869529":
                    user_id = "8"
                elif user_id == "2347033588400":
                    user_id = "2"
                user_id = str(user_id).strip()
                prop_id = str(prop_id).strip()

                if not user_id or not prop_id:
                    skipped_empty += 1
                    continue

                timestamp = created_at_old or timezone.now()
                new_obj = FloorPlanAnalysisResult(
                    message=message[:255],
                    user_id=user_id,
                    property_id=prop_id,
                    created_at=timestamp,
                    updated_at=timestamp,
                )
                new_objs_to_create.append(new_obj)
                temp_map[old_pk] = (user_id_orig, prop_id_orig, timestamp, new_obj)

            if new_objs_to_create:
                try:
                    created_objs = FloorPlanAnalysisResult.objects.using(
                        prod_db
                    ).bulk_create(
                        new_objs_to_create, batch_size=batch_size, ignore_conflicts=True
                    )
                    created_pks_dict = {
                        (o.user_id, o.property_id): (o.pk, o.created_at)
                        for o in FloorPlanAnalysisResult.objects.using(prod_db)
                        .filter(
                            user_id__in=[obj.user_id for obj in new_objs_to_create],
                            property_id__in=[
                                obj.property_id for obj in new_objs_to_create
                            ],
                        )
                        .only("pk", "user_id", "property_id", "created_at")
                    }

                    batch_proc = 0
                    for old_pk, (
                        orig_user,
                        orig_prop,
                        ts,
                        temp_obj,
                    ) in temp_map.items():
                        pk_ts_tuple = created_pks_dict.get(
                            (temp_obj.user_id, temp_obj.property_id)
                        )
                        if pk_ts_tuple:
                            new_pk, actual_created_at = pk_ts_tuple
                            old_to_new_pk_map[old_pk] = new_pk
                            analysis_creation_times[old_pk] = (
                                actual_created_at  # Store time using OLD PK as key
                            )
                            batch_proc += 1
                        else:
                            ignored_dups += 1
                    total_processed += batch_proc
                    if batch_proc > 0:
                        self.stdout.write(
                            f"  Processed {total_processed} analysis results..."
                        )
                except Exception as e:
                    self.stderr.write(self.style.ERROR(f" Error: {e}"))
                    raise

        cursor.close()
        self.stdout.write(
            f"Finished migrating {total_processed} analysis results. SkipExcl: {skipped_excluded}, SkipEmpty: {skipped_empty}, IgnoreDup: {ignored_dups}. PK map:{len(old_to_new_pk_map)}"
        )
        return old_to_new_pk_map, analysis_creation_times

    def migrate_floorplans(
        self,
        temp_db,
        prod_db,
        batch_size,
        old_to_new_analysis_pk_map,
        analysis_creation_times,
    ):
        """Migrates FloorPlan, ensuring unique calculated hashes."""
        self.stdout.write("Migrating FloorPlan...")
        old_to_new_pk = {}
        processed_hashes = set()
        total_processed = 0
        skipped_fk = 0
        skipped_hash = 0
        skipped_dup = 0
        fixed_url = 0

        # Cache analysis results needed for hash
        analysis_results_cache = {
            item["pk"]: item
            for item in FloorPlanAnalysisResult.objects.using(prod_db)
            .filter(pk__in=old_to_new_analysis_pk_map.values())
            .values("pk", "user_id", "property_id", "created_at")
        }
        self.stdout.write(
            f"  Fetched {len(analysis_results_cache)} relevant analysis results."
        )

        cursor = self._get_cursor(temp_db)
        self._execute_query(
            cursor,
            f"SELECT id, analysis_result_id, original_url FROM {OLD_FP_TABLE} ORDER BY id",
        )

        while True:
            old_rows = cursor.fetchmany(batch_size)
            if not old_rows:
                break
            new_objs_to_create = []
            temp_map = {}

            for row in old_rows:
                old_pk, old_analysis_pk, original_url = row
                new_analysis_pk = old_to_new_analysis_pk_map.get(old_analysis_pk)
                if new_analysis_pk is None:
                    skipped_fk += 1
                    continue

                analysis_result_data = analysis_results_cache.get(new_analysis_pk)
                if analysis_result_data is None:
                    skipped_fk += 1
                    continue

                if not original_url or not str(original_url).strip():
                    original_url = f"https://fake-placeholder.com/floorplan/{old_pk}"
                    fixed_url += 1
                else:
                    original_url = str(original_url).strip()

                prop_id = analysis_result_data["property_id"]
                user_id = analysis_result_data["user_id"]
                new_hash = generate_new_hash_id(prop_id, user_id, original_url)

                if new_hash is None:
                    skipped_hash += 1
                    continue
                if new_hash in processed_hashes:
                    skipped_dup += 1
                    continue
                processed_hashes.add(new_hash)

                timestamp = analysis_result_data["created_at"]  # Use parent's timestamp

                new_obj = FloorPlan(
                    analysis_result_id=new_analysis_pk,
                    original_url=original_url,
                    floorplan_id=new_hash,
                    update_count=0,
                    created_at=timestamp,
                    updated_at=timestamp,
                )
                new_objs_to_create.append(new_obj)
                temp_map[old_pk] = new_obj

            if new_objs_to_create:
                try:
                    created_objs = FloorPlan.objects.using(prod_db).bulk_create(
                        new_objs_to_create, batch_size=batch_size
                    )
                    # Map PKs
                    for old_pk, temp_obj in temp_map.items():
                        for created_obj in created_objs:
                            if temp_obj.floorplan_id == created_obj.floorplan_id:
                                old_to_new_pk[old_pk] = created_obj.pk
                                created_objs.remove(created_obj)
                                break
                        else:
                            logger.error(f"Map Fail: FP old={old_pk}")
                    total_processed += len(
                        new_objs_to_create
                    )  # Count attempts processed in batch
                    self.stdout.write(f"  Processed {total_processed} floorplans...")
                except Exception as e:
                    self.stderr.write(self.style.ERROR(f" Error: {e}"))
                    raise
        cursor.close()
        self.stdout.write(
            f"Finished FloorPlan. Proc:{total_processed}, SkipFK:{skipped_fk}, SkipHash:{skipped_hash}, SkipDup:{skipped_dup}, FixURL:{fixed_url}. PK map:{len(old_to_new_pk)}"
        )
        return old_to_new_pk

    def migrate_allfloorsdata(
        self,
        temp_db,
        prod_db,
        batch_size,
        old_to_new_fp_pk_map,
        analysis_creation_times,
    ):
        """Migrates AllFloorsData."""
        self.stdout.write(f"Migrating AllFloorsData (from {OLD_AFD_TABLE})...")
        old_to_new_pk = {}
        total_processed = 0
        skipped_fk = 0
        ignored_dups = 0
        query = f"SELECT id, floor_plan_id, json_file_url, csv_url, total_area_csv_url, image_labelme_side_by_side_url, notes FROM {OLD_AFD_TABLE} ORDER BY id"
        cursor = self._get_cursor(temp_db)
        self._execute_query(cursor, query)
        while True:
            rows = cursor.fetchmany(batch_size)
            if not rows:
                break
            new_objs = []
            temp_map = {}
            for row in rows:
                old_pk, old_fp_pk, json_u, csv_u, total_u, img_u, notes = row
                new_fp_pk = old_to_new_fp_pk_map.get(old_fp_pk)
                if new_fp_pk is None:
                    skipped_fk += 1
                    continue

                # Find timestamp via FloorPlan -> AnalysisResult relationship
                timestamp = self._get_parent_timestamp(
                    "AllFloorsData",
                    old_fp_pk,
                    FloorPlan,
                    old_to_new_fp_pk_map,
                    analysis_creation_times,
                    timezone.now(),
                )

                obj = AllFloorsData(
                    floor_plan_id=new_fp_pk,
                    json_file_url=json_u,
                    csv_url=csv_u,
                    total_area_csv_url=total_u,
                    image_labelme_side_by_side_url=img_u,
                    notes=notes,
                    created_at=timestamp,
                    updated_at=timestamp,
                )
                new_objs.append(obj)
                temp_map[old_pk] = obj
            if new_objs:
                try:
                    created = AllFloorsData.objects.using(prod_db).bulk_create(
                        new_objs, batch_size=batch_size, ignore_conflicts=True
                    )  # Use ignore for OneToOne
                    # Map PKs
                    created_pks = {
                        o.floor_plan_id: o.pk
                        for o in AllFloorsData.objects.using(prod_db)
                        .filter(floor_plan_id__in=[o.floor_plan_id for o in new_objs])
                        .only("pk", "floor_plan_id")
                    }
                    batch_proc = 0
                    for old_pk, temp_obj in temp_map.items():
                        new_pk = created_pks.get(temp_obj.floor_plan_id)
                        if new_pk:
                            old_to_new_pk[old_pk] = new_pk
                            batch_proc += 1
                        else:
                            ignored_dups += 1
                            logger.warning(
                                f"AllFloorsData old_pk={old_pk} skipped/ignored (duplicate floor_plan_id?)."
                            )
                    total_processed += batch_proc
                    if batch_proc > 0:
                        self.stdout.write(
                            f"  Processed {total_processed} AllFloorsData..."
                        )
                except Exception as e:
                    self.stderr.write(self.style.ERROR(f" Error: {e}"))
                    raise
        cursor.close()
        self.stdout.write(
            f"Finished AllFloorsData. Proc:{total_processed}, SkipFK:{skipped_fk}, IgnoredDup:{ignored_dups}. PK map:{len(old_to_new_pk)}"
        )
        return old_to_new_pk

    def migrate_planfloors(
        self,
        temp_db,
        prod_db,
        batch_size,
        old_to_new_fp_pk_map,
        analysis_creation_times,
    ):
        """Migrates PlanFloor."""
        self.stdout.write(f"Migrating PlanFloor (from {OLD_PF_TABLE})...")
        total_processed = 0
        skipped_fk = 0
        query = f"SELECT id, floor_plan_id, floor, label_me_url, json_file_url, image_url, labelme_image_url, csv_url, image_side_by_side_url FROM {OLD_PF_TABLE} ORDER BY id"
        cursor = self._get_cursor(temp_db)
        self._execute_query(cursor, query)
        while True:
            rows = cursor.fetchmany(batch_size)
            if not rows:
                break
            new_objs = []
            for row in rows:
                (
                    old_pk,
                    old_fp_pk,
                    floor,
                    lbl_u,
                    json_u,
                    img_u,
                    lblimg_u,
                    csv_u,
                    side_u,
                ) = row
                new_fp_pk = old_to_new_fp_pk_map.get(old_fp_pk)
                if new_fp_pk is None:
                    skipped_fk += 1
                    continue
                timestamp = self._get_parent_timestamp(
                    "PlanFloor",
                    old_fp_pk,
                    FloorPlan,
                    old_to_new_fp_pk_map,
                    analysis_creation_times,
                    timezone.now(),
                )

                obj = PlanFloor(
                    floor_plan_id=new_fp_pk,
                    floor=floor,
                    label_me_url=lbl_u,
                    json_file_url=json_u,
                    image_url=img_u,
                    labelme_image_url=lblimg_u,
                    csv_url=csv_u,
                    image_side_by_side_url=side_u,
                    created_at=timestamp,
                    updated_at=timestamp,
                )
                new_objs.append(obj)
            if new_objs:
                try:
                    created = PlanFloor.objects.using(prod_db).bulk_create(
                        new_objs, batch_size=batch_size
                    )
                    total_processed += len(created)
                    self.stdout.write(f"  Processed {total_processed} PlanFloors...")
                except Exception as e:
                    self.stderr.write(self.style.ERROR(f" Error: {e}"))
                    raise
        cursor.close()
        self.stdout.write(
            f"Finished PlanFloor. Processed:{total_processed}, SkipFK:{skipped_fk}."
        )

    def migrate_csvfloors(
        self,
        temp_db,
        prod_db,
        batch_size,
        old_to_new_afd_pk_map,
        analysis_creation_times,
    ):
        """Migrates CsvFloor."""
        self.stdout.write(f"Migrating CsvFloor (from {OLD_CSVFLOOR_TABLE})...")
        old_to_new_pk = {}
        total_processed = 0
        skipped_fk = 0
        query = f"SELECT id, all_floors_data_id, floor_name, calculated_total_area_metric, calculated_total_area_imperial FROM {OLD_CSVFLOOR_TABLE} ORDER BY id"
        cursor = self._get_cursor(temp_db)
        self._execute_query(cursor, query)
        while True:
            rows = cursor.fetchmany(batch_size)
            if not rows:
                break
            new_objs = []
            temp_map = {}
            for row in rows:
                old_pk, old_afd_pk, name, area_m, area_i = row
                new_afd_pk = old_to_new_afd_pk_map.get(old_afd_pk)
                if new_afd_pk is None:
                    skipped_fk += 1
                    continue
                timestamp = self._get_parent_timestamp(
                    "CsvFloor",
                    old_afd_pk,
                    AllFloorsData,
                    old_to_new_afd_pk_map,
                    analysis_creation_times,
                    timezone.now(),
                )

                obj = CsvFloor(
                    all_floors_data_id=new_afd_pk,
                    floor_name=name,
                    calculated_total_area_metric=area_m,
                    calculated_total_area_imperial=area_i,
                    created_at=timestamp,
                    updated_at=timestamp,
                )
                new_objs.append(obj)
                temp_map[old_pk] = obj
            if new_objs:
                try:
                    created = CsvFloor.objects.using(prod_db).bulk_create(
                        new_objs, batch_size=batch_size
                    )
                    # Map PKs
                    created_pks = {
                        (o.all_floors_data_id, o.floor_name): o.pk
                        for o in CsvFloor.objects.using(prod_db)
                        .filter(
                            all_floors_data_id__in=[
                                o.all_floors_data_id for o in new_objs
                            ]
                        )
                        .only("pk", "all_floors_data_id", "floor_name")
                    }
                    batch_proc = 0
                    for old_pk, temp_obj in temp_map.items():
                        new_pk = created_pks.get(
                            (temp_obj.all_floors_data_id, temp_obj.floor_name)
                        )
                        if new_pk:
                            old_to_new_pk[old_pk] = new_pk
                            batch_proc += 1
                        else:
                            logger.warning(f"CsvFloor old_pk={old_pk} mapping failed.")
                    total_processed += batch_proc
                    if batch_proc > 0:
                        self.stdout.write(f"  Processed {total_processed} CsvFloors...")
                except Exception as e:
                    self.stderr.write(self.style.ERROR(f" Error: {e}"))
                    raise
        cursor.close()
        self.stdout.write(
            f"Finished CsvFloor. Processed:{total_processed}, SkipFK:{skipped_fk}. PK map:{len(old_to_new_pk)}"
        )
        return old_to_new_pk

    def migrate_csvrooms(
        self,
        temp_db,
        prod_db,
        batch_size,
        old_to_new_csvfloor_pk_map,
        analysis_creation_times,
    ):
        """Migrates CsvRoom."""
        self.stdout.write(f"Migrating CsvRoom (from {OLD_CSVROOM_TABLE})...")
        old_to_new_pk = {}
        total_processed = 0
        skipped_fk = 0
        ignored_dups = 0
        query = f"SELECT id, floor_id, room_name, is_segment, room_id, no_of_doors, no_of_windows, no_of_room_points FROM {OLD_CSVROOM_TABLE} ORDER BY id"
        cursor = self._get_cursor(temp_db)
        self._execute_query(cursor, query)
        while True:
            rows = cursor.fetchmany(batch_size)
            if not rows:
                break
            new_objs = []
            temp_map = {}
            for row in rows:
                (
                    old_pk,
                    old_floor_pk,
                    name,
                    is_seg,
                    room_id_val,
                    doors,
                    windows,
                    points,
                ) = row
                new_floor_pk = old_to_new_csvfloor_pk_map.get(old_floor_pk)
                if new_floor_pk is None:
                    skipped_fk += 1
                    continue
                timestamp = self._get_parent_timestamp(
                    "CsvRoom",
                    old_floor_pk,
                    CsvFloor,
                    old_to_new_csvfloor_pk_map,
                    analysis_creation_times,
                    timezone.now(),
                )

                obj = CsvRoom(
                    floor_id=new_floor_pk,
                    room_name=name,
                    is_segment=is_seg,
                    room_id=room_id_val,
                    no_of_doors=doors,
                    no_of_windows=windows,
                    no_of_room_points=points,
                    created_at=timestamp,
                    updated_at=timestamp,
                )
                new_objs.append(obj)
                temp_map[old_pk] = obj
            if new_objs:
                try:
                    created = CsvRoom.objects.using(prod_db).bulk_create(
                        new_objs, batch_size=batch_size, ignore_conflicts=True
                    )
                    # Map PKs
                    created_pks = {
                        (o.floor_id, o.room_id): o.pk
                        for o in CsvRoom.objects.using(prod_db)
                        .filter(floor_id__in=[o.floor_id for o in new_objs])
                        .only("pk", "floor_id", "room_id")
                    }
                    batch_proc = 0
                    for old_pk, temp_obj in temp_map.items():
                        new_pk = created_pks.get((temp_obj.floor_id, temp_obj.room_id))
                        if new_pk:
                            old_to_new_pk[old_pk] = new_pk
                            batch_proc += 1
                        else:
                            ignored_dups += 1
                            logger.warning(
                                f"CsvRoom old_pk={old_pk} skipped/ignored (duplicate floor/room_id?)."
                            )
                    total_processed += batch_proc
                    if batch_proc > 0:
                        self.stdout.write(f"  Processed {total_processed} CsvRooms...")
                except Exception as e:
                    self.stderr.write(self.style.ERROR(f" Error: {e}"))
                    raise
        cursor.close()
        self.stdout.write(
            f"Finished CsvRoom. Processed:{total_processed}, SkipFK:{skipped_fk}, IgnoredDup:{ignored_dups}. PK map:{len(old_to_new_pk)}"
        )
        return old_to_new_pk

    def migrate_csvroom_details(
        self,
        temp_db,
        prod_db,
        batch_size,
        old_to_new_csvroom_pk_map,
        analysis_creation_times,
    ):
        """Migrates CsvRoomPixelData, CsvRoomDimensions, CsvRoomScalingFactors."""
        self.stdout.write("Migrating CsvRoom Details (Pixel, Dimensions, Scaling)...")
        # Note: These are OneToOne fields to CsvRoom
        # Map old column names to new field names carefully
        model_map = {
            "Pixel": (
                OLD_CSVROOMPIXEL_TABLE,
                CsvRoomPixelData,
                {
                    "id": None,
                    "room_id": "room_id",
                    "min_x_pixels": "min_x_pixels",
                    "min_y_pixels": "min_y_pixels",
                    "max_x_pixels": "max_x_pixels",
                    "max_y_pixels": "max_y_pixels",
                    "max_area_pixels": "max_area_pixels",
                    "actual_area_pixels": "actual_area_pixels",
                    "pixel_ratio": "pixel_ratio",
                },
            ),
            "Dimensions": (
                OLD_CSVROOMDIM_TABLE,
                CsvRoomDimensions,
                {
                    "id": None,
                    "room_id": "room_id",
                    "dimensions_imperial": "dimensions_imperial",
                    "dimensions_metric": "dimensions_metric",
                    "max_area_metric": "max_area_metric",
                    "max_area_imperial": "max_area_imperial",
                    "calculated_sq_area_metric": "calculated_sq_area_metric",
                    "calculated_area_imperial": "calculated_area_imperial",
                },
            ),
            "Scaling": (
                OLD_CSVROOMSCALE_TABLE,
                CsvRoomScalingFactors,
                {
                    "id": None,
                    "room_id": "room_id",
                    "scale_metric": "scale_metric",
                    "scale_imperial": "scale_imperial",
                },
            ),
        }

        for name, (old_table, NewModel, col_map) in model_map.items():
            self.stdout.write(f"  Migrating {name}...")
            total_processed = 0
            skipped_fk = 0
            ignored_dups = 0
            old_cols_str = ", ".join(
                [f'"{c}"' for c in col_map.keys() if c != "id"]
            )  # Quote column names if needed
            query = f"SELECT id, {old_cols_str} FROM {old_table} ORDER BY id"
            cursor = self._get_cursor(temp_db)
            self._execute_query(cursor, query)

            while True:
                rows = cursor.fetchmany(batch_size)
                if not rows:
                    break
                new_objs = []
                for row in rows:
                    old_pk = row[0]
                    old_room_pk = row[
                        1
                    ]  # Assuming room_id is always the second column selected
                    new_room_pk = old_to_new_csvroom_pk_map.get(old_room_pk)
                    if new_room_pk is None:
                        skipped_fk += 1
                        continue
                    timestamp = self._get_parent_timestamp(
                        f"CsvRoom{name}",
                        old_room_pk,
                        CsvRoom,
                        old_to_new_csvroom_pk_map,
                        analysis_creation_times,
                        timezone.now(),
                    )

                    data = {
                        "room_id": new_room_pk,
                        "created_at": timestamp,
                        "updated_at": timestamp,
                    }
                    old_col_list = list(
                        col_map.keys()
                    )  # Get ordered list of old columns queried (including id)
                    for i, value in enumerate(row):
                        if i == 0:
                            continue  # Skip old_pk
                        model_field_name = col_map[old_col_list[i]]
                        if (
                            model_field_name and model_field_name != "room_id"
                        ):  # Skip id and already set room_id
                            data[model_field_name] = value

                    new_objs.append(NewModel(**data))

                if new_objs:
                    try:
                        created = NewModel.objects.using(prod_db).bulk_create(
                            new_objs, batch_size=batch_size, ignore_conflicts=True
                        )
                        total_processed += len(created)
                        self.stdout.write(
                            f"    Processed {total_processed} {name} details..."
                        )
                    except Exception as e:
                        self.stderr.write(
                            self.style.ERROR(f" Error creating {name} details: {e}")
                        )
                        raise
            cursor.close()
            self.stdout.write(
                f"  Finished {name}. Processed:{total_processed}, SkipFK:{skipped_fk}."
            )

    def migrate_rawrows(
        self,
        temp_db,
        prod_db,
        batch_size,
        old_to_new_afd_pk_map,
        analysis_creation_times,
    ):
        """Migrates AllFloorsCsvData (renamed from AllFloorsCsvRawRow)."""
        self.stdout.write(f"Migrating AllFloorsCsvData (from {OLD_RAWROW_TABLE})...")
        total_processed = 0
        skipped_fk = 0
        cursor = self._get_cursor(temp_db)
        # Select all columns assumed to exist in the old raw row table
        cursor.execute(
            f"""
             SELECT id, all_floors_data_id, floor_name, room_name, is_segment, room_id,
                 no_of_door, no_of_window, no_of_room_points, min_x_pixels_csv, min_y_pixels_csv,
                 max_x_pixels_csv, max_y_pixels_csv, dimensions_imperial, dimensions_metric,
                 max_area_metric_csv, max_area_imperial_csv, max_area_pixels_csv,
                 actual_area_pixels_csv, pixel_ratio_csv, scale_metric_csv, scale_imperial_csv,
                 calculated_sq_area_metric_csv, calculated_floor_total_sq_area_metric,
                 calculated_area_imperial_csv, calculated_floor_total_sq_area_imperial
             FROM {OLD_RAWROW_TABLE} ORDER BY id
         """
        )

        while True:
            old_rows = cursor.fetchmany(batch_size)
            if not old_rows:
                break
            new_objs = []
            for row in old_rows:
                (
                    old_pk,
                    old_afd_pk,
                    floor_name,
                    room_name,
                    is_segment,
                    room_id_val,
                    no_of_door,
                    no_of_window,
                    no_of_room_points,
                    min_x,
                    min_y,
                    max_x,
                    max_y,
                    dim_imp,
                    dim_met,
                    max_a_met,
                    max_a_imp,
                    max_a_pix,
                    act_a_pix,
                    pix_ratio,
                    scale_met,
                    scale_imp,
                    calc_sq_met,
                    calc_floor_met,
                    calc_a_imp,
                    calc_floor_imp,
                ) = row

                new_afd_pk = old_to_new_afd_pk_map.get(old_afd_pk)
                if new_afd_pk is None:
                    skipped_fk += 1
                    continue
                timestamp = self._get_parent_timestamp(
                    "AllFloorsCsvData",
                    old_afd_pk,
                    AllFloorsData,
                    old_to_new_afd_pk_map,
                    analysis_creation_times,
                    timezone.now(),
                )

                new_obj = AllFloorsCsvData(  # Use NEW model name
                    all_floors_data_id=new_afd_pk,
                    floor_name=floor_name,
                    room_name=room_name,
                    is_segment=is_segment,
                    room_id=room_id_val,
                    no_of_door=no_of_door,
                    no_of_window=no_of_window,
                    no_of_room_points=no_of_room_points,
                    min_x_pixels=min_x,
                    min_y_pixels=min_y,
                    max_x_pixels=max_x,
                    max_y_pixels=max_y,
                    dimensions_imperial=dim_imp,
                    dimensions_metric=dim_met,
                    max_area_metric=max_a_met,
                    max_area_imperial=max_a_imp,
                    max_area_pixels=max_a_pix,
                    actual_area_pixels=act_a_pix,
                    pixel_ratio=pix_ratio,
                    scale_metric=scale_met,
                    scale_imperial=scale_imp,
                    calculated_sq_area_metric=calc_sq_met,
                    calculated_floor_total_sq_area_metric=calc_floor_met,
                    calculated_area_imperial=calc_a_imp,
                    calculated_floor_total_sq_area_imperial=calc_floor_imp,
                    created_at=timestamp,
                    updated_at=timestamp,
                )
                new_objs.append(new_obj)
            if new_objs:
                try:
                    created = AllFloorsCsvData.objects.using(prod_db).bulk_create(
                        new_objs, batch_size=batch_size
                    )
                    total_processed += len(created)
                    self.stdout.write(
                        f"  Processed {total_processed} raw rows (AllFloorsCsvData)..."
                    )
                except Exception as e:
                    self.stderr.write(self.style.ERROR(f" Error: {e}"))
                    raise
        cursor.close()
        self.stdout.write(
            f"Finished migrating AllFloorsCsvData. Processed:{total_processed}, SkipFK:{skipped_fk}"
        )

    def migrate_totalareas(
        self,
        temp_db,
        prod_db,
        batch_size,
        old_to_new_afd_pk_map,
        analysis_creation_times,
    ):
        """Migrates TotalAreasCsvData (renamed from TotalAreaData)."""
        self.stdout.write(
            f"Migrating TotalAreasCsvData (from {OLD_TOTALAREA_TABLE})..."
        )
        total_processed = 0
        skipped_fk = 0
        ignored_dups = 0
        query = f"SELECT id, all_floors_data_id, area_name, square_meters, square_feet, total_floors, total_named_rooms, total_segments, total_points, total_objects, total_door_objects, total_window_objects, total_stair_objects, list_of_objects, total_actual_pixels, metric_scale, imperial_scale, input_image_tokens, input_text_tokens, output_text_tokens FROM {OLD_TOTALAREA_TABLE} ORDER BY id"
        cursor = self._get_cursor(temp_db)
        self._execute_query(cursor, query)
        while True:
            rows = cursor.fetchmany(batch_size)
            if not rows:
                break
            new_objs = []
            temp_map = {}
            for row in rows:
                (
                    old_pk,
                    old_afd_pk,
                    area_n,
                    sqm,
                    sqf,
                    floors,
                    rooms,
                    seg,
                    points,
                    obj_tot,
                    obj_d,
                    obj_w,
                    obj_s,
                    list_o,
                    pix,
                    ms,
                    iscale,
                    in_img,
                    in_txt,
                    out_txt,
                ) = row
                new_afd_pk = old_to_new_afd_pk_map.get(old_afd_pk)
                if new_afd_pk is None:
                    skipped_fk += 1
                    continue
                timestamp = self._get_parent_timestamp(
                    "TotalAreasCsvData",
                    old_afd_pk,
                    AllFloorsData,
                    old_to_new_afd_pk_map,
                    analysis_creation_times,
                    timezone.now(),
                )

                obj = TotalAreasCsvData(  # Use NEW model name
                    all_floors_data_id=new_afd_pk,
                    area_name=area_n,
                    square_meters=sqm,
                    square_feet=sqf,
                    total_floors=floors,
                    total_named_rooms=rooms,
                    total_segments=seg,
                    total_points=points,
                    total_objects=obj_tot,
                    total_door_objects=obj_d,
                    total_window_objects=obj_w,
                    total_stair_objects=obj_s,
                    list_of_objects=list_o,
                    total_actual_pixels=pix,
                    metric_scale=ms,
                    imperial_scale=iscale,
                    input_image_tokens=in_img,
                    input_text_tokens=in_txt,
                    output_text_tokens=out_txt,
                    created_at=timestamp,
                    updated_at=timestamp,
                )
                new_objs.append(obj)
                temp_map[old_pk] = obj
            if new_objs:
                try:
                    created = TotalAreasCsvData.objects.using(prod_db).bulk_create(
                        new_objs, batch_size=batch_size, ignore_conflicts=True
                    )
                    # Map PKs (match on FK + name?)
                    created_pks = {
                        (o.all_floors_data_id, o.area_name): o.pk
                        for o in TotalAreasCsvData.objects.using(prod_db)
                        .filter(
                            all_floors_data_id__in=[
                                o.all_floors_data_id for o in new_objs
                            ]
                        )
                        .only("pk", "all_floors_data_id", "area_name")
                    }
                    batch_proc = 0
                    for old_pk, temp_obj in temp_map.items():
                        new_pk = created_pks.get(
                            (temp_obj.all_floors_data_id, temp_obj.area_name)
                        )
                        if new_pk:
                            batch_proc += 1  # Don't need map for this leaf model
                        else:
                            ignored_dups += 1
                            logger.warning(
                                f"TotalAreasCsvData old_pk={old_pk} skipped/ignored (duplicate afd/area_name?)."
                            )
                    total_processed += batch_proc
                    if batch_proc > 0:
                        self.stdout.write(
                            f"  Processed {total_processed} TotalAreasCsvData..."
                        )
                except Exception as e:
                    self.stderr.write(self.style.ERROR(f" Error: {e}"))
                    raise
        cursor.close()
        self.stdout.write(
            f"Finished migrating TotalAreasCsvData. Processed:{total_processed}, SkipFK:{skipped_fk}, IgnoredDup:{ignored_dups}."
        )

import os
import shutil


def delete_migrations_and_dbsqlite(startpath):
    for root, dirs, files in os.walk(startpath, topdown=True):
        # Skip venv directory
        dirs[:] = [d for d in dirs if d not in ["venv"]]

        # Delete migration files but keep the __init__.py within migrations folder
        if "migrations" in dirs:
            migrations_path = os.path.join(root, "migrations")
            for filename in os.listdir(migrations_path):
                if filename != "__init__.py":
                    file_path = os.path.join(migrations_path, filename)
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                        print(f"Deleted {file_path}")

        # Delete all __pycache__ folders recursively
        if "__pycache__" in dirs:
            pycache_path = os.path.join(root, "__pycache__")
            shutil.rmtree(pycache_path)
            print(f"Deleted {pycache_path}")

        # Delete db.sqlite3 file if found
        for file in files:
            if file == "db.sqlite3":
                os.remove(os.path.join(root, file))
                print(f"Deleted {os.path.join(root, file)}")


if __name__ == "__main__":
    project_path = input("Enter the path to your Django project directory: ")
    delete_migrations_and_dbsqlite(project_path)

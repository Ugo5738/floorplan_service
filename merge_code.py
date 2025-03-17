import os
import sys


def should_exclude(file_path):
    # Exclude .DS_Store files
    if os.path.basename(file_path) == ".DS_Store":
        return True
    # Exclude files that are inside any directory named "migrations"
    if "migrations" in file_path.split(os.sep):
        return True
    # Exclude log files
    if file_path.lower().endswith(".log"):
        return True
    # Add more exclusion rules here if necessary
    return False


def merge_code(paths, output_file="merged_code.txt"):
    with open(output_file, "w", encoding="utf-8") as outfile:
        for path in paths:
            if os.path.isfile(path):
                # Process individual file
                outfile.write(f"# {path}\n")
                try:
                    with open(path, "r", encoding="utf-8") as infile:
                        outfile.write(infile.read())
                except Exception as e:
                    outfile.write(f"// Error reading file: {e}\n")
                outfile.write("\n\n")
            elif os.path.isdir(path):
                # Process directory recursively
                for root, dirs, files in os.walk(path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        if should_exclude(file_path):
                            continue

                        # Get the path relative to the base directory for a cleaner header
                        relative_path = os.path.relpath(file_path, path)
                        outfile.write(f"# {path}/{relative_path}\n")
                        try:
                            with open(file_path, "r", encoding="utf-8") as infile:
                                outfile.write(infile.read())
                        except Exception as e:
                            outfile.write(f"// Error reading file: {e}\n")
                        outfile.write("\n\n")
            else:
                # If the path does not exist or is not a file/directory, note it.
                outfile.write(f"// Path not found or invalid: {path}\n\n")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(
            "Usage: python merge_code.py <output_file> <directory_or_file1> [directory_or_file2 ...]"
        )
    else:
        output_file = sys.argv[1]
        paths = sys.argv[2:]
        merge_code(paths, output_file)

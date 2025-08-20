import yaml
import sys

def get_nested(data, path):
    keys = path.split('.')
    for key in keys:
        if data is None:
            return None
        if isinstance(data, dict):
            data = data.get(key)
        elif isinstance(data, list):
            try:
                key = int(key)
                if key < len(data):
                    data = data[key]
                else:
                    return None
            except (ValueError, IndexError):
                return None
        else:
            return None
    return data

def set_nested(data, path, value, create_if_missing=True):
    keys = path.split('.')
    current = data
    for i, key in enumerate(keys[:-1]):
        if isinstance(current, list):
            try:
                key = int(key)
                if key >= len(current):
                    if create_if_missing:
                        current.extend([None] * (key - len(current) + 1))
                    else:
                        raise IndexError("List index out of range")
                
                if current[key] is None and create_if_missing:
                    # Look ahead to see if next key is int or not
                    try:
                        int(keys[i+1])
                        current[key] = []
                    except ValueError:
                        current[key] = {}

                current = current[key]

            except ValueError:
                raise TypeError(f"Cannot access list with non-integer key: {key}")
        elif isinstance(current, dict):
            if key not in current and create_if_missing:
                # Look ahead to see if next key is int or not
                try:
                    int(keys[i+1])
                    current[key] = []
                except ValueError:
                    current[key] = {}
            current = current.get(key)
        
        if current is None:
            raise KeyError(f"Key '{keys[i]}' not found in path and create_if_missing is false or path is invalid")


    final_key = keys[-1]
    if isinstance(current, list):
        try:
            final_key = int(final_key)
            if final_key >= len(current):
                if create_if_missing:
                    current.extend([None] * (final_key - len(current) + 1))
                else:
                    raise IndexError("List index out of range")
            current[final_key] = value
        except ValueError:
            raise TypeError(f"Cannot access list with non-integer key: {final_key}")
    elif isinstance(current, dict):
        current[final_key] = value
    else:
        raise TypeError(f"Cannot set value on a non-dict/non-list type: {type(current)}")


def main():
    if len(sys.argv) < 3:
        print("Usage: python manifest_edit.py <file_path> <command> [args...]")
        print("Commands:")
        print("  get <dot_path>")
        print("  set <dot_path> <value_yaml>")
        print("  append <dot_path> <value_yaml>")
        sys.exit(1)

    file_path = sys.argv[1]
    command = sys.argv[2]

    try:
        with open(file_path, 'r') as f:
            data = yaml.safe_load(f)
    except FileNotFoundError:
        print(f"Error: File not found at {file_path}")
        sys.exit(1)
    except yaml.YAMLError as e:
        print(f"Error parsing YAML file {file_path}: {e}")
        sys.exit(1)

    if command == 'get':
        if len(sys.argv) != 4:
            print("Usage: python manifest_edit.py <file_path> get <dot_path>")
            sys.exit(1)
        dot_path = sys.argv[3]
        value = get_nested(data, dot_path)
        if value is not None:
            print(yaml.dump(value, default_flow_style=False, sort_keys=False))
        else:
            print(f"Path '{dot_path}' not found.")
            
    elif command in ['set', 'append']:
        if len(sys.argv) != 5:
            print(f"Usage: python manifest_edit.py <file_path> {command} <dot_path> <value_yaml>")
            sys.exit(1)
        
        dot_path = sys.argv[3]
        value_str = sys.argv[4]

        try:
            value_to_process = yaml.safe_load(value_str)
        except yaml.YAMLError as e:
            print(f"Error parsing value YAML '{value_str}': {e}")
            sys.exit(1)

        try:
            if command == 'set':
                set_nested(data, dot_path, value_to_process, create_if_missing=True)
            elif command == 'append':
                target_list = get_nested(data, dot_path)
                if not isinstance(target_list, list):
                    print(f"Error: Path '{dot_path}' does not point to a list for append operation.")
                    sys.exit(1)
                target_list.append(value_to_process)
            
            with open(file_path, 'w') as f:
                yaml.dump(data, f, default_flow_style=False, sort_keys=False)
            print(f"Successfully performed '{command}' on '{file_path}' at path '{dot_path}'")

        except (KeyError, IndexError, TypeError) as e:
            print(f"Error processing path '{dot_path}': {e}")
            sys.exit(1)
    
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()

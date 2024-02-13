import os

import yaml

# Read environment variables from app.yaml
app_yaml_path = os.environ.get("APP_YAML_PATH", "app.yaml")
STRING_ENCODING = os.environ.get("PYTHONIOENCODING", "utf-8")


def load_environment_variables() -> None:
    """
    Load environment variables from an App YAML file.

    Reads an App YAML file specified by `app_yaml_path`, extracts the 'variables'
    section, and updates the current environment variables with the values provided
    in the 'name' and 'defaultValue' fields of the variables list.

    Parameters:
    - None: The function reads the App YAML file path from a predefined variable.

    Returns:
    - None: Updates the environment variables based on the contents of the App YAML file.

    Example:
    ```python
    load_environment_variables()
    ```

    Raises:
    - FileNotFoundError: If the specified App YAML file is not found.
    - yaml.YAMLError: If there is an error parsing the YAML file.
    - KeyError: If the 'variables' section is missing or not a list in the YAML file.
    - TypeError: If the 'variables' section contains invalid data types.
    """
    with open(app_yaml_path, "r", encoding=STRING_ENCODING) as file:
        config = yaml.safe_load(file)
        if "variables" in config and isinstance(config["variables"], list):
            # Convert the list of variables to a dictionary
            variables_dict = {
                variable["name"]: variable["defaultValue"]
                for variable in config["variables"]
            }
            os.environ.update(variables_dict)


def headers_serializer(headers):
    """
    Serialize a list of header tuples into a list of tuples with UTF-8 encoded values.

    Parameters:
    - headers (list): A list of tuples representing headers.

    Returns:
    list: A new list of tuples with headers, where values are UTF-8 encoded.
    """
    return [(key, str(value).encode(STRING_ENCODING)) for key, value in headers]

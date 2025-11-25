
import yaml
import sys
from coinbase.rest import RESTClient

def load_config(config_path="config.yaml"):
    with open(config_path, "r") as f:
        return yaml.safe_load(f)

def main():
    config = load_config()
    api_config = config["api"]
    client = RESTClient(api_key=api_config["key_name"], api_secret=api_config["private_key"])
    product_id = config["trading"]["product_id"]
    
    print(f"Fetching info for {product_id}...")
    try:
        response = client.get_product(product_id)
        print("\nResponse attributes:")
        print(dir(response))
        print("\nResponse dictionary (if available):")
        if hasattr(response, "to_dict"):
            print(response.to_dict())
        else:
            print(response)
            
        if hasattr(response, "base_increment"):
            print(f"\nbase_increment: {response.base_increment}")
        else:
            print("\nbase_increment NOT FOUND in response attributes")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()

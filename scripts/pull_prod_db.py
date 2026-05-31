import os
import sys
import argparse
import logging

# Dynamically append the parent directory of this script to sys.path to allow imports from config
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from pymongo import MongoClient
from pymongo.errors import PyMongoError
from config import settings

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

def migrate_database(auto_confirm: bool = False):
    """
    Connects to the AWS EC2 production MongoDB instance, reads all documents 
    and custom index structures, and replicates them locally.
    """
    # 1. Retrieve & validate the production connection string
    prod_uri = settings.PROD_MONGO_URI
    if not prod_uri or prod_uri.strip() == "":
        logger.critical(
            "\n❌ Error: PROD_MONGO_URI is not configured in your .env file!\n"
            "Please open your .env file and configure:\n"
            "PROD_MONGO_URI=\"mongodb://username:password@ec2-public-ip:port/dbname?authSource=dbname\"\n"
        )
        sys.exit(1)

    local_uri = settings.MONGO_URI
    target_db_name = settings.MONGO_DB_NAME

    logger.info("Initializing migration resources...")
    try:
        # Establish Source and Target clients
        src_client = MongoClient(prod_uri, serverSelectionTimeoutMS=5000)
        dest_client = MongoClient(local_uri, serverSelectionTimeoutMS=3000)

        # Test connections
        src_client.admin.command("ping")
        dest_client.admin.command("ping")
        
        # Get target databases
        # Find database name from credentials or fallback to configuration settings
        src_db_name = src_client.get_database().name
        if src_db_name == "admin" or src_db_name == "local":
            src_db_name = target_db_name # Fallback to config if URI had no explicit dbname path
            
        src_db = src_client[src_db_name]
        dest_db = dest_client[target_db_name]

        logger.info(f"Successfully connected to Source (EC2: '{src_db_name}') and Target (Local: '{target_db_name}')")

    except PyMongoError as conn_err:
        logger.critical(f"Connection/Authentication Failure: {conn_err}")
        sys.exit(1)

    # 2. Get list of collections to migrate, filtering out system tables
    try:
        all_collections = src_db.list_collection_names()
        collections_to_migrate = [
            c for c in all_collections 
            if not c.startswith("system.") and c not in ["admin", "config", "local"]
        ]
        
        if not collections_to_migrate:
            logger.warning("No custom collections found in source database to migrate.")
            src_client.close()
            dest_client.close()
            return

        logger.info(f"Found {len(collections_to_migrate)} custom collections to migrate: {collections_to_migrate}")

    except PyMongoError as list_err:
        logger.critical(f"Failed to fetch collection details from EC2: {list_err}")
        src_client.close()
        dest_client.close()
        sys.exit(1)

    # 3. Interactive confirmation prompt
    if not auto_confirm:
        print("\n" + "="*60)
        print("🚨 WARNING: DATABASE MIGRATION IN PROGRESS 🚨")
        print("="*60)
        print(f"Source Database (EC2)   : {prod_uri.split('@')[-1] if '@' in prod_uri else prod_uri}")
        print(f"Target Database (Local) : {local_uri} -> DB: '{target_db_name}'")
        print("This operation will WIPE out all local matching collections and indexes!")
        print("="*60)
        confirm = input("Are you absolutely sure you want to proceed? [y/N]: ").strip().lower()
        if confirm not in ["y", "yes"]:
            logger.info("Migration cancelled by user.")
            src_client.close()
            dest_client.close()
            sys.exit(0)

    # 4. Migrate each collection
    for col_name in collections_to_migrate:
        logger.info(f"--- Migrating Collection: '{col_name}' ---")
        
        src_col = src_db[col_name]
        dest_col = dest_db[col_name]

        # 4a. Drop existing local collection to start fresh
        logger.info(f"Wiping local target collection '{col_name}'...")
        dest_col.drop()

        # 4b. Pull documents in batches of 1000 (RAM-safe)
        total_docs = src_col.count_documents({})
        logger.info(f"Found {total_docs} documents in source collection '{col_name}' to migrate.")

        if total_docs > 0:
            cursor = src_col.find({})
            batch = []
            migrated_count = 0
            batch_size = 1000

            for doc in cursor:
                batch.append(doc)
                if len(batch) >= batch_size:
                    dest_col.insert_many(batch)
                    migrated_count += len(batch)
                    logger.info(f" -> Migrated {migrated_count}/{total_docs} documents...")
                    batch = []

            # Insert any remaining documents
            if batch:
                dest_col.insert_many(batch)
                migrated_count += len(batch)
                logger.info(f" -> Migrated {migrated_count}/{total_docs} documents...")

            logger.info(f"✅ Successfully migrated {migrated_count} records for '{col_name}'.")
        else:
            logger.info(f"Collection '{col_name}' is empty. Nothing to transfer.")

        # 4c. Copy index definitions from production database (including 2dsphere spatial indexes)
        logger.info(f"Copying index structures from source for '{col_name}'...")
        try:
            indexes = src_col.list_indexes()
            index_copied_count = 0
            for idx in indexes:
                idx_name = idx.get("name")
                # Skip the default _id_ index since MongoDB creates it automatically
                if idx_name == "_id_":
                    continue

                # Parse index key configuration (e.g. [("_geoloc", "2dsphere")])
                keys = list(idx["key"].items())
                
                # Filter out standard pymongo fields to extract optional params
                options = {k: v for k, v in idx.items() if k not in ["key", "v", "ns"]}
                
                logger.info(f" -> Creating local index: name='{idx_name}', keys={keys}, options={options}")
                dest_col.create_index(keys, **options)
                index_copied_count += 1
            
            logger.info(f"✅ Copied {index_copied_count} custom indexes for '{col_name}'.")

            # Fallback: Always guarantee that our primary profiles collection has a 2dsphere index on '_geoloc'
            if col_name == settings.MONGO_COLLECTION_NAME:
                # Check if a 2dsphere index exists in the current collection indexes
                existing_indexes = list(dest_col.list_indexes())
                has_geospatial_index = any(
                    any(val == "2dsphere" for val in idx.get("key", {}).values())
                    for idx in existing_indexes
                )
                if not has_geospatial_index:
                    logger.info(" -> No geospatial index found. Creating fallback 2dsphere index on '_geoloc'...")
                    dest_col.create_index(
                        [("_geoloc", "2dsphere")],
                        name="geoloc_2dsphere_idx",
                        background=True
                    )
                    logger.info("✅ Fallback geospatial index 'geoloc_2dsphere_idx' created successfully.")

        except PyMongoError as idx_err:
            logger.error(f"Failed to copy indexes for collection '{col_name}': {idx_err}")

    print("\n" + "="*60)
    print("🎉 DATABASE MIGRATION COMPLETED SUCCESSFULLY! 🎉")
    print("="*60 + "\n")

    src_client.close()
    dest_client.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Database Pull Utility: Pull AWS EC2 Production collections and indexes locally."
    )
    parser.add_argument(
        "-y", "--yes", 
        action="store_true", 
        help="Skip interactive confirmation prompts (useful for script automation)."
    )
    args = parser.parse_args()
    
    migrate_database(auto_confirm=args.yes)

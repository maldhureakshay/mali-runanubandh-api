import logging
from fastapi.concurrency import run_in_threadpool
from firebase_admin import firestore
from app.community.models.post import AuthorSnapshot, ProfileSnapshot
from app.community.enums import PostType
from app.core.dependencies import AuthenticatedUser
from database import db_manager

logger = logging.getLogger(__name__)

def _fetch_user_from_firestore(uid: str) -> dict:
    try:
        db = firestore.client()
        doc_ref = db.collection("users").document(uid)
        doc = doc_ref.get()
        if doc.exists:
            return doc.to_dict() or {}
        return {}
    except Exception as e:
        logger.error("Failed to fetch user %s from Firestore: %s", uid, e)
        return {}

async def get_author_snapshot_from_firestore(current_user: AuthenticatedUser) -> AuthorSnapshot:
    """
    Fetches the AuthorSnapshot from the Firebase 'users' collection.
    Falls back to claims if the document is not found or fails.
    """
    user_data = await run_in_threadpool(_fetch_user_from_firestore, current_user.uid)
    
    profile_ids = user_data.get("profile_ids", [])
    profile_id = profile_ids[0] if profile_ids else None
    
    return AuthorSnapshot(
        userId=current_user.uid,
        profileId=profile_id or current_user.claims.get("profileId", "unknown"),
        fullName=user_data.get("displayName", current_user.name or current_user.email or "Community Member"),
        verified=user_data.get("is_verified", current_user.claims.get("verified", False)),
        paidMember=user_data.get("status", current_user.claims.get("paidMember", False))
    )

async def get_profile_snapshot_from_mongo(profile_id: str) -> ProfileSnapshot:
    """
    Fetches basic profile info from the MongoDB 'profiles' collection to populate Post metadata.
    """
    if not profile_id:
        return ProfileSnapshot(profileId="", fullName="Unknown")

    try:
        profiles_coll = db_manager.get_collection()
        # MongoDB uses string 'original_id' for Firebase uid, or string '_id'
        profile_data = await profiles_coll.find_one({"original_id": profile_id})
        if not profile_data:
            profile_data = await profiles_coll.find_one({"_id": profile_id})
            
        if not profile_data:
            return ProfileSnapshot(profileId=profile_id, fullName="Member")
            
        # Determine display name
        first_name = profile_data.get("first_name", "")
        last_name = profile_data.get("last_name", "")
        full_name = f"{first_name} {last_name}".strip()
        if not full_name:
            full_name = "Member"
            
        # Determine image URL
        image_url = None
        images = profile_data.get("images", [])
        if images and isinstance(images, list) and len(images) > 0:
            image_url = images[0]
        elif profile_data.get("biodata_image_url"):
            image_url = profile_data.get("biodata_image_url")
            
        return ProfileSnapshot(
            profileId=profile_id,
            fullName=full_name,
            imageUrl=image_url
        )
    except Exception as e:
        logger.error("Failed to fetch profile %s from MongoDB: %s", profile_id, e)
        return ProfileSnapshot(profileId=profile_id, fullName="Member")

async def enrich_posts_with_profile_snapshots(posts_data: list[dict]) -> list[dict]:
    """
    Iterates through serialized post dictionaries and asynchronously resolves 
    profile snapshots for MARRIAGE_SUCCESS posts.
    """
    for post in posts_data:
        logger.info(f"Checking post {post.get('_id')} of type {post.get('type')}")
        if post.get("type") == PostType.MARRIAGE_SUCCESS:
            metadata = post.get("metadata", {})
            logger.info(f"Found metadata: {metadata}")
            if metadata:
                p1_id = metadata.get("person1ProfileId")
                p2_id = metadata.get("person2ProfileId")
                
                logger.info(f"p1: {p1_id}, p2: {p2_id}")
                
                if p1_id:
                    p1_snap = await get_profile_snapshot_from_mongo(p1_id)
                    logger.info(f"p1_snap: {p1_snap}")
                    metadata["person1Snapshot"] = p1_snap.model_dump(mode="json")
                if p2_id:
                    p2_snap = await get_profile_snapshot_from_mongo(p2_id)
                    logger.info(f"p2_snap: {p2_snap}")
                    metadata["person2Snapshot"] = p2_snap.model_dump(mode="json")
    return posts_data

import urllib.request
import urllib.parse
import json
import sys
import time

BASE_URL = "http://127.0.0.1:8000"

def make_request(path: str, params: dict = None) -> dict:
    """
    Helper to send a synchronous GET request using standard library urllib.
    """
    url = f"{BASE_URL}{path}"
    if params:
        query_string = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        url = f"{url}?{query_string}"
    
    # logger equivalent
    print(f"GET -> {url}")
    
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.status == 200:
                return json.loads(response.read().decode("utf-8"))
            else:
                print(f"Error: Received HTTP {response.status}", file=sys.stderr)
                sys.exit(1)
    except urllib.error.HTTPError as e:
        print(f"HTTP Error {e.code}: {e.read().decode('utf-8')}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Network Error: {e}", file=sys.stderr)
        sys.exit(1)

def run_tests():
    print("==============================================")
    print("    STARTING MATRIMONY GEO API INTEGRATION TESTS")
    print("==============================================")

    # 1. Health check verification
    print("\n--- Test 1: Verification of Service Health Check ---")
    health = make_request("/api/profiles/health")
    print(f"Response: {health}")
    assert health["status"] == "healthy", "Expected service status to be 'healthy'"
    assert health["database"] == "connected", "Expected database connection to be active"
    print("✅ Test 1 Passed!")

    # 2. Geo Near sorting from Pune Center (lat=18.5204, lng=73.8567)
    print("\n--- Test 2: GeoNear Sorting & Proximity Order (Pune Base) ---")
    # Coordinates of Pune Center
    pune_lat, pune_lng = 18.5204, 73.8567
    result = make_request("/api/profiles/nearby", {"lat": pune_lat, "lng": pune_lng, "limit": 10})
    
    profiles = result["data"]
    total = result["total"]
    print(f"Found {total} active profiles near Pune.")
    
    # Assert sorting order: Snehal (Pune ~0km) -> Rajesh (Hadapsar ~10km) -> Rahul (Mumbai ~120km) ...
    names = [p["full_name"] for p in profiles]
    distances = [p["distance_km"] for p in profiles]
    
    for idx, (name, dist) in enumerate(zip(names, distances)):
        print(f" [{idx + 1}] {name:<25} | Distance: {dist:.2f} km")
        
    # Ensure distances are strictly ascending
    assert all(distances[i] <= distances[i+1] for i in range(len(distances)-1)), "Profiles are not sorted nearest first!"
    print("✅ Test 2 Passed!")

    # 3. Filtering by gender
    print("\n--- Test 3: Gender Matching Filters (Females only) ---")
    female_result = make_request("/api/profiles/nearby", {
        "lat": pune_lat, 
        "lng": pune_lng, 
        "gender": "female",
        "limit": 10
    })
    female_profiles = female_result["data"]
    print(f"Found {female_result['total']} female profiles.")
    for p in female_profiles:
        print(f" - {p['full_name']} ({p['gender']})")
        assert p["gender"].lower() == "female", f"Expected only female profiles, got {p['gender']}"
    print("✅ Test 3 Passed!")

    # 4. Filtering by verification status
    print("\n--- Test 4: Profile Verification Filters ---")
    verified_result = make_request("/api/profiles/nearby", {
        "lat": pune_lat, 
        "lng": pune_lng, 
        "is_verified": True,
        "limit": 10
    })
    verified_profiles = verified_result["data"]
    print(f"Verified profiles count: {verified_result['total']}")
    for p in verified_profiles:
        assert p.get("is_verified") is True, f"Expected only verified profiles, got unverified: {p['full_name']}"
    print("✅ Test 4 Passed!")

    # 5. Offset-based Pagination limits & has_more
    print("\n--- Test 5: Pagination Offsets & Metadata ---")
    page1 = make_request("/api/profiles/nearby", {
        "lat": pune_lat, 
        "lng": pune_lng, 
        "page": 1,
        "limit": 2
    })
    print(f"Page 1 (Limit=2): {[p['full_name'] for p in page1['data']]}")
    assert len(page1["data"]) == 2, "Expected exactly 2 profiles on Page 1"
    assert page1["has_more"] is True, "Expected has_more to be True"
    assert page1["total"] > 2, "Expected total count to reflect all near profiles"

    page2 = make_request("/api/profiles/nearby", {
        "lat": pune_lat, 
        "lng": pune_lng, 
        "page": 2,
        "limit": 2
    })
    print(f"Page 2 (Limit=2): {[p['full_name'] for p in page2['data']]}")
    assert len(page2["data"]) == 2, "Expected exactly 2 profiles on Page 2"
    
    # Assert that overlap doesn't occur
    p1_names = [p["id"] for p in page1["data"]]
    p2_names = [p["id"] for p in page2["data"]]
    intersection = set(p1_names).intersection(set(p2_names))
    assert not intersection, "Pagination returned duplicate records across pages!"
    print("✅ Test 5 Passed!")

    # 6. Admin Dashboard metrics
    print("\n--- Test 6: Admin Dashboard Metrics ---")
    dashboard = make_request("/api/admin/dashboard")
    print(f"Dashboard metrics: {dashboard}")
    assert "totalUsers" in dashboard, "Expected totalUsers in dashboard metrics"
    assert "activeUsers" in dashboard, "Expected activeUsers in dashboard metrics"
    assert "totalProfiles" in dashboard, "Expected totalProfiles in dashboard metrics"
    assert "activeProfiles" in dashboard, "Expected activeProfiles in dashboard metrics"
    
    # Test dashboard with active_since cutoff
    dashboard_cutoff = make_request("/api/admin/dashboard", {"active_since": "2026-02-09T00:00:00"})
    print(f"Dashboard metrics with cutoff 2026-02-09: {dashboard_cutoff}")
    assert "activeUsersSinceCutoff" in dashboard_cutoff, "Expected activeUsersSinceCutoff in dashboard metrics"
    print("✅ Test 6 Passed!")

    # 7. Admin Users Pagination & Search
    print("\n--- Test 7: Admin Users Pagination & Search ---")
    users_result = make_request("/api/admin/users", {"page": 1, "limit": 5})
    print(f"Users found: {users_result['total']}")
    assert "data" in users_result, "Expected 'data' key in response"
    assert "total" in users_result, "Expected 'total' key in response"
    print("✅ Test 7 Passed!")

    print("\n==============================================")
    print("    ALL INTEGRATION TESTS PASSED SUCCESSFULLY! 🎉")
    print("==============================================")

if __name__ == "__main__":
    # Small delay to ensure server fully processed logs if triggered via subprocess
    run_tests()

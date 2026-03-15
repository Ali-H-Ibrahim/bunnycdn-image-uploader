"""
Test scenarios for the failed image retry feature.

This file provides test cases and validation for different retry scenarios.
Run manually to verify the retry feature works as expected.
"""

import json
from app.parsing import extract_image_locations, update_image_url, cleanup_removed_images, REMOVE_MARKER


def test_nested_paths():
    """Test Scenario 1: Nested paths are preserved during retry."""
    print("\n=== Test 1: Nested Paths ===")
    
    product = {
        "id": "TEST1",
        "variants": [
            {"color": "red", "Image": "http://example.com/red.jpg"},
            {"color": "blue", "Image": "http://example.com/blue.jpg"}
        ]
    }
    
    # Extract locations
    locations = extract_image_locations(product, "variants[].Image")
    assert len(locations) == 2, f"Expected 2 locations, got {len(locations)}"
    
    # Simulate failure and mark for removal
    first_loc = locations[0]
    assert first_loc.keys == ["variants", 0, "Image"], f"Unexpected keys: {first_loc.keys}"
    update_image_url(product, first_loc.keys, REMOVE_MARKER)
    
    # Simulate retry success - update with CDN URL
    update_image_url(product, first_loc.keys, "https://cdn.example.com/red.jpg")
    
    # Verify update worked
    assert product["variants"][0]["Image"] == "https://cdn.example.com/red.jpg"
    assert product["variants"][1]["Image"] == "http://example.com/blue.jpg"
    
    print("✓ Nested path update successful")
    print(f"  Updated: {product['variants'][0]['Image']}")
    print(f"  Preserved: {product['variants'][1]['Image']}")


def test_duplicate_urls():
    """Test Scenario 2: Duplicate URLs tracked independently."""
    print("\n=== Test 2: Duplicate URLs ===")
    
    product = {
        "id": "TEST2",
        "Images": [
            "http://example.com/same.jpg",
            "http://example.com/same.jpg",
            "http://example.com/different.jpg"
        ]
    }
    
    locations = extract_image_locations(product, "Images[]")
    assert len(locations) == 3, f"Expected 3 locations, got {len(locations)}"
    
    # All locations have the same URL but different keys
    assert locations[0].original_url == locations[1].original_url
    assert locations[0].keys != locations[1].keys
    assert locations[0].keys == ["Images", 0]
    assert locations[1].keys == ["Images", 1]
    
    # Update only the first duplicate
    update_image_url(product, locations[0].keys, "https://cdn.example.com/same-1.jpg")
    
    assert product["Images"][0] == "https://cdn.example.com/same-1.jpg"
    assert product["Images"][1] == "http://example.com/same.jpg"
    assert product["Images"][2] == "http://example.com/different.jpg"
    
    print("✓ Duplicate URLs handled independently")
    print(f"  First duplicate: {product['Images'][0]}")
    print(f"  Second duplicate: {product['Images'][1]}")


def test_cleanup_behavior():
    """Test Scenario 3: Cleanup removes only marked items."""
    print("\n=== Test 3: Cleanup Behavior ===")
    
    product = {
        "id": "TEST3",
        "Images": ["img1.jpg", "img2.jpg", "img3.jpg"],
        "mainImage": "main.jpg"
    }
    
    # Extract and mark middle item for removal
    locations = extract_image_locations(product, "Images[]")
    update_image_url(product, locations[1].keys, REMOVE_MARKER)
    
    # Mark scalar field for removal
    main_loc = extract_image_locations(product, "mainImage")[0]
    update_image_url(product, main_loc.keys, REMOVE_MARKER)
    
    # Apply cleanup
    cleanup_removed_images(product, ["Images[]", "mainImage"])
    
    # Verify array shrunk
    assert len(product["Images"]) == 2
    assert "img2.jpg" not in product["Images"]
    assert product["Images"] == ["img1.jpg", "img3.jpg"]
    
    # Verify scalar became None
    assert product["mainImage"] is None
    
    print("✓ Cleanup removes marked items correctly")
    print(f"  Array after cleanup: {product['Images']}")
    print(f"  Scalar after cleanup: {product['mainImage']}")


def test_retry_success_simulation():
    """Test Scenario 4: Simulate late success in retry."""
    print("\n=== Test 4: Retry Success Simulation ===")
    
    product = {
        "id": "TEST4",
        "Images": ["img1.jpg", "img2.jpg", "img3.jpg"]
    }
    
    # Simulate initial failure on img2
    locations = extract_image_locations(product, "Images[]")
    failed_loc = locations[1]
    
    # Store error with keys
    error_record = {
        "product_index": 0,
        "product_id": "TEST4",
        "image_path": failed_loc.path_display,
        "keys": failed_loc.keys,
        "source_url": failed_loc.original_url,
        "status": "failed",
        "error_type": "http_error"
    }
    
    # Simulate retry success - update using stored keys
    update_image_url(product, error_record["keys"], "https://cdn.example.com/img2.jpg")
    
    assert product["Images"][1] == "https://cdn.example.com/img2.jpg"
    
    print("✓ Retry success updates correct position")
    print(f"  Original: {failed_loc.original_url}")
    print(f"  Updated: {product['Images'][1]}")
    print(f"  Keys used: {error_record['keys']}")


def test_error_filtering():
    """Test Scenario 6: Only retriable errors are retried."""
    print("\n=== Test 6: Error Filtering ===")
    
    errors = [
        {"error_type": "http_error", "status": "failed"},
        {"error_type": "invalid_source", "status": "failed"},
        {"error_type": "not_found", "status": "not_found"},
        {"error_type": "upload_error", "status": "failed"},
        {"error_type": "timeout", "status": "failed"},
    ]
    
    # Simulate retry filter logic
    retriable = [
        err for err in errors
        if err["error_type"] not in ("invalid_source", "not_found")
        and err["status"] != "not_found"
    ]
    
    assert len(retriable) == 3, f"Expected 3 retriable, got {len(retriable)}"
    
    retriable_types = [e["error_type"] for e in retriable]
    assert "invalid_source" not in retriable_types
    assert "not_found" not in retriable_types
    assert "http_error" in retriable_types
    assert "upload_error" in retriable_types
    
    print("✓ Error filtering works correctly")
    print(f"  Total errors: {len(errors)}")
    print(f"  Retriable: {len(retriable)}")
    print(f"  Types: {retriable_types}")


def test_keys_serialization():
    """Test that keys field is JSON-serializable."""
    print("\n=== Test 7: Keys Serialization ===")
    
    product = {
        "variants": [
            {"Image": "test.jpg"}
        ]
    }
    
    locations = extract_image_locations(product, "variants[].Image")
    loc = locations[0]
    
    error = {
        "keys": loc.keys,
        "image_path": loc.path_display,
        "source_url": loc.original_url
    }
    
    # Ensure it can be serialized to JSON
    json_str = json.dumps(error)
    parsed = json.loads(json_str)
    
    assert parsed["keys"] == ["variants", 0, "Image"]
    assert isinstance(parsed["keys"][1], int)
    
    print("✓ Keys field is JSON-serializable")
    print(f"  Serialized: {json_str}")


def run_all_tests():
    """Run all test scenarios."""
    print("=" * 60)
    print("Running Retry Feature Test Scenarios")
    print("=" * 60)
    
    tests = [
        test_nested_paths,
        test_duplicate_urls,
        test_cleanup_behavior,
        test_retry_success_simulation,
        test_error_filtering,
        test_keys_serialization,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"✗ {test.__name__} FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ {test.__name__} ERROR: {e}")
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"Test Results: {passed} passed, {failed} failed")
    print("=" * 60)
    
    if failed == 0:
        print("🎉 All tests passed!")
    else:
        print("⚠️  Some tests failed. Please review.")


if __name__ == "__main__":
    run_all_tests()

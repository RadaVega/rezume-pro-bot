#!/usr/bin/env python3
"""
Debug script to test VK attachment handling.
# ⚠️  SSL verification disabled for testing only - do not use in production
Does NOT modify main.py - safe to run alongside working bot.
"""

import json
import requests
import os

# Your bot's webhook URL
WEBHOOK_URL = "https://rezume-pro-bot--andreokounev77.replit.app/webhook"

# Test VK message payloads
TEST_PAYLOADS = {
    "text_only": {
        "type": "message_new",
        "object": {
            "message": {
                "id": 999,
                "from_id": 1085183520,
                "text": "/start",
                "attachments": []
            }
        },
        "group_id": 237022345
    },
    
    "pdf_attachment": {
        "type": "message_new",
        "object": {
            "message": {
                "id": 999,
                "from_id": 1085183520,
                "text": "",
                "attachments": [
                    {
                        "type": "doc",
                        "doc": {
                            "id": 123456,
                            "owner_id": 237022345,
                            "title": "test_resume.pdf",
                            "ext": "pdf",
                            "url": "https://vk.com/doc_test_url"
                        }
                    }
                ]
            }
        },
        "group_id": 237022345
    },
    
    "docx_attachment": {
        "type": "message_new",
        "object": {
            "message": {
                "id": 999,
                "from_id": 1085183520,
                "text": "",
                "attachments": [
                    {
                        "type": "doc",
                        "doc": {
                            "id": 123457,
                            "owner_id": 237022345,
                            "title": "test_resume.docx",
                            "ext": "docx",
                            "url": "https://vk.com/doc_test_url"
                        }
                    }
                ]
            }
        },
        "group_id": 237022345
    }
}


def test_webhook(test_name, payload):
    """Send test payload to webhook and check response."""
    print(f"\n{'='*60}")
    print(f"🧪 Testing: {test_name}")
    print(f"{'='*60}")
    
    try:
        response = requests.post(
            WEBHOOK_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10, verify=False
        )
        
        print(f"✅ HTTP Status: {response.status_code}")
        print(f"✅ Response: {response.text[:200]}")
        
        # Log what we sent
        attachments = payload.get("object", {}).get("message", {}).get("attachments", [])
        print(f"📎 Attachments sent: {len(attachments)}")
        if attachments:
            for att in attachments:
                print(f"   - Type: {att.get('type')}, Ext: {att.get('doc', {}).get('ext', 'N/A')}")
        
        return response.status_code == 200
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_health():
    """Test health endpoint."""
    print(f"\n{'='*60}")
    print(f"🏥 Testing Health Endpoint")
    print(f"{'='*60}")
    
    try:
        url = WEBHOOK_URL.replace("/webhook", "/health")
        response = requests.get(url, timeout=10, verify=False)
        print(f"✅ Status: {response.status_code}")
        print(f"✅ Response: {json.dumps(response.json(), indent=2)}")
        return response.status_code == 200
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def main():
    print("🔍 ResumePro AI - Attachment Debug Tool")
    print(f"📡 Webhook URL: {WEBHOOK_URL}")
    print(f"{'='*60}")
    
    # Test health first
    health_ok = test_health()
    if not health_ok:
        print("\n❌ Bot is not healthy! Check if it's running.")
        return
    
    # Test each payload
    results = {}
    for name, payload in TEST_PAYLOADS.items():
        results[name] = test_webhook(name, payload)
    
    # Summary
    print(f"\n{'='*60}")
    print(f"📊 Test Summary")
    print(f"{'='*60}")
    for name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} - {name}")
    
    # Check Replit Console for detailed logs
    print(f"\n📋 Now check Replit Console for detailed logs:")
    print(f"   Look for: '📨 user=...' and '📎 Attachment types:...'")
    print(f"   If attachment not detected, logs will show: attachments=[]")


if __name__ == "__main__":
    main()

#!/usr/bin/env python
"""
Test script to verify S3 connectivity and operations using the credentials in .env file.
This script will:
1. Connect to S3
2. Upload a test file
3. Verify the file exists
4. Delete the test file
"""
import os
import sys
import boto3
from botocore.exceptions import ClientError
from io import BytesIO
from PIL import Image
import numpy as np
from datetime import datetime
from dotenv import load_dotenv
import requests

# Load environment variables from .env
load_dotenv()

# S3 configuration
AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
AWS_STORAGE_BUCKET_NAME = os.getenv('AWS_STORAGE_BUCKET_NAME')

print(f"Testing S3 connection with:")
print(f"Bucket: {AWS_STORAGE_BUCKET_NAME}")
print(f"Access Key ID: {AWS_ACCESS_KEY_ID[:5]}...{AWS_ACCESS_KEY_ID[-4:]}")
print(f"Secret Access Key: {AWS_SECRET_ACCESS_KEY[:5]}...{AWS_SECRET_ACCESS_KEY[-4:] if AWS_SECRET_ACCESS_KEY else None}")

if not all([AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_STORAGE_BUCKET_NAME]):
    print("Error: Missing required S3 credentials in .env file")
    sys.exit(1)

# Create test image with timestamp
def create_test_image():
    img = Image.new('RGB', (100, 100), color=(73, 109, 137))
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    img_io = BytesIO()
    img.save(img_io, format='JPEG')
    img_io.seek(0)
    return img_io

# Initialize S3 client
try:
    s3_client = boto3.client(
        's3',
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY
    )
    print("✅ Successfully created S3 client")
except Exception as e:
    print(f"❌ Failed to create S3 client: {str(e)}")
    sys.exit(1)

# Test 1: Check if bucket exists
try:
    s3_client.head_bucket(Bucket=AWS_STORAGE_BUCKET_NAME)
    print(f"✅ Bucket {AWS_STORAGE_BUCKET_NAME} exists and is accessible")
except ClientError as e:
    error_code = e.response['Error']['Code']
    if error_code == '404':
        print(f"❌ Bucket {AWS_STORAGE_BUCKET_NAME} does not exist")
    elif error_code == '403':
        print(f"❌ Access denied to bucket {AWS_STORAGE_BUCKET_NAME}")
    else:
        print(f"❌ Error checking bucket: {str(e)}")
    sys.exit(1)

# Test 2: Upload a test file
test_key = f"test_uploads/test_image_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
try:
    test_data = create_test_image()
    s3_client.upload_fileobj(
        test_data, 
        AWS_STORAGE_BUCKET_NAME, 
        test_key,
        ExtraArgs={
            'ContentType': 'image/jpeg'
            # ACL disabled since the bucket does not support ACLs
        }
    )
    print(f"✅ Successfully uploaded test file to {test_key}")
except Exception as e:
    print(f"❌ Failed to upload test file: {str(e)}")
    sys.exit(1)

# Test 3: Verify the file exists
try:
    s3_client.head_object(Bucket=AWS_STORAGE_BUCKET_NAME, Key=test_key)
    print(f"✅ Verified test file exists at {test_key}")
    
    # Construct the URL to the uploaded file
    object_url = f"https://{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com/{test_key}"
    print(f"✅ File accessible at: {object_url}")
    
    # Test if the file is publicly accessible by making an HTTP request
    try:
        response = requests.get(object_url, timeout=5)
        if response.status_code == 200:
            print("✅ File is publicly accessible")
        else:
            print(f"⚠️ File may not be publicly accessible: HTTP status {response.status_code}")
    except requests.RequestException as e:
        print(f"⚠️ Could not verify public access: {str(e)}")
    
except ClientError as e:
    print(f"❌ Failed to verify test file exists: {str(e)}")

# Test 4: Clean up by deleting the test file
try:
    s3_client.delete_object(Bucket=AWS_STORAGE_BUCKET_NAME, Key=test_key)
    print(f"✅ Successfully deleted test file {test_key}")
except Exception as e:
    print(f"⚠️ Failed to delete test file (will need manual cleanup): {str(e)}")

# Test 5: Test GIF to JPEG conversion logic similar to our implemented function
print("\n🧪 Testing GIF to JPEG conversion logic")
try:
    # Create a simple GIF image in memory
    gif_data = BytesIO()
    Image.new('RGB', (100, 100), color='red').save(gif_data, format='GIF')
    gif_data.seek(0)
    
    # Convert to JPEG
    with Image.open(gif_data) as img:
        if img.mode in ('RGBA', 'P'):
            rgb_img = img.convert('RGB')
        else:
            rgb_img = img
            
        # Save as JPEG
        jpeg_data = BytesIO()
        rgb_img.save(jpeg_data, format='JPEG', quality=90)
        jpeg_data.seek(0)
        
        # Upload to S3
        test_key = f"test_uploads/converted_test_gif_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        s3_client.upload_fileobj(
            jpeg_data,
            AWS_STORAGE_BUCKET_NAME,
            test_key,
            ExtraArgs={
                'ContentType': 'image/jpeg'
                # ACL disabled since the bucket does not support ACLs
            }
        )
        print(f"✅ Successfully converted GIF to JPEG and uploaded to {test_key}")
        
        # Generate the URL to the file
        object_url = f"https://{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com/{test_key}"
        print(f"✅ Converted file accessible at: {object_url}")
        
        # Clean up
        s3_client.delete_object(Bucket=AWS_STORAGE_BUCKET_NAME, Key=test_key)
        print(f"✅ Cleaned up test file {test_key}")
except Exception as e:
    print(f"❌ Error in GIF to JPEG conversion test: {str(e)}")

print("\n✅ All tests completed!")

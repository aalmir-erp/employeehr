#!/bin/bash

# Replace these with your device's details
LOCAL_IP="192.168.1.100"  # Change to your device's actual IP
USERNAME="admin"
PASSWORD="Mir@Dxb60"

echo "==== Testing Hikvision Device API at $LOCAL_IP ===="

# Test device info endpoint (basic connectivity check)
echo "1. Testing Device Info Endpoint..."
curl -s -k --user "$USERNAME:$PASSWORD" "http://$LOCAL_IP/ISAPI/System/deviceInfo" | grep -E 'deviceName|serialNumber|firmwareVersion'
echo ""

# Test employee list endpoint
echo "2. Testing Employee List Endpoint..."
curl -s -k --user "$USERNAME:$PASSWORD" "http://$LOCAL_IP/ISAPI/AccessControl/UserInfo/Record?format=json" 
echo ""

# Test attendance logs endpoint (adjust dates as needed)
echo "3. Testing Attendance Logs Endpoint..."
curl -s -k -X POST --user "$USERNAME:$PASSWORD" \
  -H "Content-Type: application/xml" \
  -d "<AcsEventCond><searchID>1</searchID><searchResultPosition>0</searchResultPosition><maxResults>10</maxResults><major>5</major><minor>75</minor><startTime>$(date -d '24 hours ago' '+%Y-%m-%dT%H:%M:%SZ')</startTime><endTime>$(date '+%Y-%m-%dT%H:%M:%SZ')</endTime></AcsEventCond>" \
  "http://$LOCAL_IP/ISAPI/AccessControl/AcsEvent?format=json" 
echo ""

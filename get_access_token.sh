#!/bin/sh

# Define output colors
GREEN='\033[0;32m'
ORANGE='\033[38;2;255;165;0m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Prompt user for input
echo -ne "${ORANGE}Matrix Homeserver: ${NC}"
read homeserver
echo -ne "${ORANGE}Admin Username: ${NC}"
read username
echo -ne "${ORANGE}Password: ${NC}"
read -s password
echo
echo

# Use curl to authenticate user via Matrix Login API endpoint
# Method used for capturing STDOUT and STDERR to separate variable implemention method provided in stack overflow response below:
# https://stackoverflow.com/questions/13806626/capture-both-stdout-and-stderr-in-bash#26827443
. <({ http_transfer_details=$({ http_response=$(curl -s -w "%{stderr}%{json}" -X POST -H "Content-Type: application/json" -d '{"type": "m.login.password", "identifier": {"type": "m.id.user",  "user": "'${username}'"}, "password": "'${password}'", "device_id": "maubot-invite"}' https://${homeserver}/_matrix/client/r0/login); } 2>&1; declare -p http_response >&2); declare -p http_transfer_details; } 2>&1)

# Check curl exit status
exitcode=$(echo $http_transfer_details | tr { '\n' | tr , '\n' | tr } '\n' | grep "exitcode" | awk  -F';' '{print $1}' | cut -f2- -d':' | sed 's/"//g')
if [[ $exitcode -ne 0 ]]; then
  errormsg=$(echo $http_transfer_details | tr { '\n' | tr , '\n' | tr } '\n' | grep "errormsg" | awk  -F';' '{print $1}' | cut -f2- -d':' | sed 's/"//g')
else
  # Check HTTP status code
  http_code=$(echo $http_transfer_details | tr { '\n' | tr , '\n' | tr } '\n' | grep "http_code" | awk  -F';' '{print $1}' | cut -f2- -d':' | sed 's/"//g')
  if [[ $http_code -ne 200 ]]; then
    errormsg=$(echo $http_response | tr { '\n' | tr , '\n' | tr } '\n' | grep "error" | awk  -F'"' '{print $4}')
  else
    # Extract access token from json response and display
    access_token=$(echo $http_response | tr { '\n' | tr , '\n' | tr } '\n' | grep "access_token" | awk  -F'"' '{print $4}')
    echo -e "${GREEN}Access Token: ${access_token}${NC}"
    exit 0
  fi
fi

# Display error message
echo -e "${RED}Error: ${errormsg}${NC}"
exit 1
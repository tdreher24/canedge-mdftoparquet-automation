# CANedge MDF to Parquet Automation

> **Fork Notice:** This is a fork of [CSS-Electronics/canedge-mdftoparquet-automation](https://github.com/CSS-Electronics/canedge-mdftoparquet-automation) with additional production-ready AWS Lambda deployment automation. The original repository provides cloud functions for multi-cloud platforms (AWS, Google Cloud, Azure), while this fork adds streamlined GitHub Actions workflows and CloudFormation templates specifically for AWS Lambda deployments.

## What's Added in This Fork

- **GitHub Actions Workflow** (`.github/workflows/lambda-automation.yml`) - Automated build and deployment pipeline
- **CloudFormation Template** (`deployment/cloudformation/aws-lambda-automation.json`) - Infrastructure as Code for Lambda function
- **OIDC Authentication** - Secure AWS deployment without storing access keys
- **Deployment Documentation** (`deployment/README.md`) - Complete setup guide for AWS deployments

See [deployment/README.md](deployment/README.md) for deployment instructions.

---

## Original Repository Description

This repository contains cloud functions for automatically decoding CANedge MDF log files to Parquet files **locally**, as well as on **Amazon AWS**, **Google Cloud** and **Azure** platforms. These functions are triggered when new MDF files are uploaded to a cloud storage bucket, process them using DBC decoding, and store the results in Parquet format in an output bucket. Further, the repository includes code for performing backlog processing and Parquet data lake trip summary aggregation.

> [!NOTE]  
> See the [CANedge Intro](https://www.csselectronics.com/pages/can-bus-hardware-software-docs) (Process/MF4 decoders) for cloud-specific deployment guidance

---------

## Repository Structure

The repository is organized into three main directories:

### 1. `mdftoparquet/` - Single File Processing

Contains the cloud function code for processing individual MDF files when they are uploaded to cloud storage.

#### Cloud Function Entry Points
- `lambda_function.py` - AWS Lambda function entry point
- `main.py` - Google Cloud Function entry point
- `function_app.py` - Azure Function entry point

#### Cloud-Specific Configuration
- `azure-function-root/` - Azure function configuration files
- `google-function-root/` - Google Cloud Function configuration files

### 2. `mdftoparquet-backlog/` - Backlog Processing

Contains scripts for batch processing existing MDF files in cloud storage buckets.

- `process_backlog_amazon.py` - Script for processing backlog files in Amazon
- `process_backlog_amazon_entry.py` - Extracts above script from Lambda into Glue and runs it
- `process_backlog_container.py` - Script for processing backlog files in Azure via container
- `process_backlog_google.py` - Script for processing backlog files in Google 

### 3. `aggregation/` - Parquet Aggregation Processing

Contains scripts for aggregating Parquet files to trip summray level (as a supplement to the existing Parquet data lake data). The scripts are structured similarly to the backlog scripts.

### 4. `local-testing/` - Local Testing Environment

Contains utilities and scripts for local development and testing.

- `run_test.py` - Main test runner for simulating cloud function invocation locally
- `local_invocation.py` - Utility for invoking cloud functions with proper environment setup
- `utils_testing.py` - Utility functions for creating test events and loading credentials

### Core Modules
Shared functionality is in the `modules/` directory at the repository root:
- `mdf_to_parquet.py` - Main processing logic for converting MDF to Parquet
- `cloud_functions.py` - Cloud provider specific operations (download/upload/list files)
- `utils.py` - Utility functions for decoding, custom messages, and event detection
- `custom_message_functions.py` - Functions for creating calculated signals
- `aggregation.py` - Functionality for aggregation of Parquet data lakes
- `functions.py` - Additional helper functions

### Decoders
- `mdf2parquet_decode` - Linux executable for DBC decoding MDF files to Parquet (used in cloud environments)
- `mdf2parquet_decode.exe` - Windows executable for DBC decoding (used for local testing)

---------

## Credential Files

Credential files for local testing are stored in the `local-testing/creds/` directory with one file per cloud provider:
- `local-testing/creds/amazon-creds.json` - AWS credentials
- `local-testing/creds/google-creds.json` - Google Cloud service account key
- `local-testing/creds/azure-creds.json` - Azure storage connection strings

These credential files are used during local testing and should contain the necessary permissions to:
- Read from the input bucket/container
- Read/write from/to the output bucket/container

### Credentials Format

Each cloud provider requires a specific credential file format - see the `json-examples/creds-examples/` folder for the cloud specific structures. Below we outline how you can populate each of these when you've deployed the cloud specific automation workflow as per the CANedge Intro:

- **Google credentials**: This can be found in your input bucket (named `<id>-service-account-key.json`)
- **Amazon credentials**: This can be found in the CloudFormation stack outputs (at the bottom)
- **Azure credentials**: This can be found in the Azure Function/Settings/Environment variables

---------

## Local Testing

The repository includes several scripts and batch files in the `local-testing/` directory that allow you to test the cloud functions locally before deployment. Make sure to update the `creds/` folder if testing one of the cloud scripts. The repository contains `*.bat` files for various test cases that can be easily modified with your own input bucket/container details. 

---------


### Advanced Functionality

Advanced functionality for the automation integration relies on uploading specific JSON files to the input bucket:

- **Custom Messages**: Define custom calculated signals via `custom-messages.json` 
- **Event Detection**: Configure event detection via `events.json` 
- **Device-Specific DBC**: Configure device-specific DBC decoding via `dbc-groups.json`
- **Decryption**: Decrypt `MFE`, `MFM` files via `passwords.json` 
- **Geofences**: Configure dynamic geofence definitions via `geofences.json`

The `json-examples/` folder contains examples showing the structure of the above files. Details on these topics can be found in the CANedge Intro.

### Geofence Configuration

You can define custom geofences by uploading a `geofences.json` file to the input bucket. This file will be used by the `custom_geofences` function in `custom_message_functions.py` to dynamically load geofence definitions instead of using hardcoded values. To activate the creation of custom geofences, you will need to also add the `custom-messages.json` to your input bucket and reference the `custom_geofences` function.

```json
[
    {
        "id": 1,
        "name": "Home Base",
        "latitude": 56.072706,
        "longitude": 10.103398,
        "radius": 0.2
    },
    {
        "id": 2,
        "name": "Service Center",
        "latitude": 56.116626,
        "longitude": 10.154564,
        "radius": 0.3
    }
]
```

Each geofence requires the following fields:
- **id**: Numeric identifier for the geofence (used in the `GeofenceId` output signal)
- **name**: Descriptive name for the geofence
- **latitude**: Geographic latitude in decimal degrees (-90 to 90)
- **longitude**: Geographic longitude in decimal degrees (-180 to 180)
- **radius**: Radius of the geofence in kilometers (must be greater than 0)

---------

## Backlog Processing

To process a large number of MDF files efficiently, backlog processing scripts are provided for each cloud provider and local environments. These scripts read a `backlog.json` file from the root of the input bucket/folder, which contains a list of MDF files to process. You can test this locally via the `--backlog` flag:

```bash
python local-testing/run_test.py \
  --cloud <Amazon|Google|Azure|Local> \
  --input-bucket <bucket-name-or-folder> \
  --backlog
```

See the CANedge Intro for guidance on executing backlog processing directly within your cloud, where the relevant scripts will be deployed automatically as part of the default integration.


> [!NOTE]  
> Backlog processing takes your advanced functionality into account (event detection, custom messages etc). However, event notification is disabled during backlog processing.


### Backlog File Structure

The backlog.json file must use the following format with required configuration fields:

```json
{
  "config": {
    "batch_size": {
      "min": 10,
      "max": 256
    }
  },
  "files": [
    "2F6913DB/",
    "ABCDEF12/00000088/",
    "2F6913DB/00000086/00000001-62961868.MF4",
    "2F6913DB/00000086/00000003-62977DFB.MF4"
  ]
}
```

- **config**: Required configuration section
  - **batch_size**: Required batch size configuration
    - **min**: Minimum items to trigger batch optimization (required)
    - **max**: Maximum items per batch (required)
- **files**: Required array of file paths/prefixes to process

All configuration parameters are required - the system will validate the structure of the backlog.json file and fail if any required field is missing.

### Prefix Types and File Paths

You can specify three types of entries in the backlog file:

1. **Device Prefixes**: Path to a device folder (e.g., `"2F6913DB/"`) - processes all sessions under that device
2. **Session Prefixes**: Path to a specific session (e.g., `"2F6913DB/00000088/"`) - processes all files in that session
3. **Individual Files**: Complete file path (e.g., `"2F6913DB/00000086/00000001-62961868.MF4"`) - processes a specific file

**Note**: For prefixes (device or session), trailing slashes are optional - they will be automatically added if missing. File paths should not have trailing slashes.

---------

## Aggregation Processing

The repository includes functionality for aggregating Parquet data into trip summaries across all cloud providers. These scripts read an `aggregations.json` file from the root of the input bucket, which defines how Parquet data should be aggregated into trips. You can test this locally via the `--aggregate` flag:

```bash
python local-testing/run_test.py \
  --cloud <Amazon|Google|Azure|Local> \
  --input-bucket <bucket-name-or-folder> \
  --aggregate
```

See the CANedge Intro for guidance on executing aggregation processing directly within your cloud, where the relevant scripts will be deployed automatically as part of the default integration.

### Aggregation Configuration Structure

The aggregations.json file defines how to identify and process trips in the Parquet data:

```json
{
  "config": {
    "date": {
      "mode": "specific_period",
      "start_date": "2023-01-01",
      "end_date": "2023-12-31"
    },
    "trip": {
      "trip_gap_min": 10,
      "trip_min_length_min": 1
    }
  },
  "device_clusters": [
    {
      "devices": ["2F6913DB", "ABCDEF12"],
      "cluster": "cluster1"
    }
  ],
  "cluster_details": [
    {
      "clusters": ["cluster1"],
      "details": {
        "trip_identifier": {"message": "CAN2_GnssSpeed"},
        "aggregations": [
          {
            "message": "CAN2_GnssSpeed",
            "signal": ["Speed"],
            "aggregation": ["avg", "max"]
          },
          {
            "message": "CAN2_GnssPosition",
            "signal": ["Latitude", "Longitude"],
            "aggregation": ["first", "last"]
          }
        ]
      }
    }
  ]
}
```

- **config**: Top-level configuration section
  - **date**: Date range configuration
    - **mode**: Either "specific_period" (use explicit dates) or "previous_day" (automatic)
    - **start_date/end_date**: Required for "specific_period" mode (format: YYYY-MM-DD)
  - **trip**: Trip detection parameters
    - **trip_gap_min**: Minutes of inactivity to consider a new trip has started
    - **trip_min_length_min**: Minimum trip length in minutes to be considered valid

- **device_clusters**: Group devices into logical clusters
  - **devices**: List of device IDs (serial numbers) to process
  - **cluster**: Name assigned to this group of devices

- **cluster_details**: Processing configuration for each cluster
  - **clusters**: List of cluster names to apply these settings to
  - **details**: Processing configuration
    - **trip_identifier**: Message used to identify trips
    - **aggregations**: List of signals to aggregate
      - **message**: Parquet data lake message folder name
      - **signal**: List of signal names to aggregate
      - **aggregation**: List of aggregation functions (avg, max, min, sum, first, last, etc.)

---------

## Deployment

### Preparing Deployment Packages

The repository includes a script to generate deployment ZIP files, scripts and containers for the various cloud platforms. These are primarily designed for developer use or by CSS Electronics for updating deployment stacks. For details on deploying the cloud functions as a CANedge end user, see the CANedge Intro.

---------

## Backround - How The MF4 to Parquet Decoding Works

1. **Trigger**: A new MDF file (`.MF4`, `.MFC`, `.MFE`, or `.MFM`) is uploaded to the input bucket/container
2. **Processing**:
   - The cloud function is triggered
   - The MDF file and necessary DBC files are downloaded to the function's temporary storage
   - `mdf2parquet_decode` converts the MDF data to Parquet format using DBC decoding
   - Custom message calculations are performed if configured
   - Event detection is performed if configured
3. **Output**: 
   - Parquet files are created for each unique CAN message in the structure: `<deviceid>/<message>/<yyyy>/<mm>/<dd>/<xyz>.parquet`
   - Files are uploaded to the output bucket/container (named with `-parquet` suffix)
   - For events, notifications may be sent (e.g., via SNS in AWS)

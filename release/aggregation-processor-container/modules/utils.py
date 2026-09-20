from .cloud_functions import download_object, list_objects, list_objects_with_pagination, upload_object, publish_notification

# Function for cleaning up temporary MDF files
def clean_tmp(base, logger):
    import os
    
    # Define valid MDF file extensions
    valid_extensions = ('.MF4', '.MFC', '.MFE', '.MFM')
    
    try:
        logger.info(f"Listing contents of {base} dir:")
        logger.info(os.listdir(base))
        for name in os.listdir(base):
            p = os.path.join(base, name)
            try:
                if os.path.isfile(p) and name.upper().endswith(valid_extensions):
                    os.remove(p)
                    logger.info(f"Removed MDF file: {p}")
                elif os.path.isfile(p):
                    logger.info(f"Skipped file (not MDF): {p}")
                elif os.path.isdir(p):
                    logger.info(f"Skipped directory: {p}")
            except Exception as e:
                logger.warning("tmp cleanup skipped %s: %s", p, e)
        logger.info("tmp directory cleaned")
    except FileNotFoundError:
        logger.info(FileNotFoundError)
        pass  
        
# Class for downloading objects required by the Lambda
class DownloadObjects:
    def __init__(self, cloud, storage_client, bucket_input, tmp_input_dir, log_file_object_path, logger):
        self.logger = logger
        self.cloud = cloud
        self.storage_client = storage_client
        self.bucket_input = bucket_input
        self.tmp_input_dir = tmp_input_dir
        self.log_file_object_path = log_file_object_path

    # -----------------------------------------------
    # Extract device ID (note: Only works if the CANedge S3 file structure is used)
    def extract_device_id(self):
        import re
        
        device_id = ""
        parts = self.log_file_object_path.parts
        
        # Check if the path has at least 3 parts and 1st part matches device ID syntax
        if len(parts) == 3 and re.match("[0-9A-F]{8}$", parts[0]):
            # The device_id is expected to be the first part of the path
            device_id = parts[0]
            self.logger.info(f"Device ID: {device_id}")
        else:
            self.logger.info(f"Unable to extract device_id (log file does not use CANedge S3 path)")
        
        return device_id
    
    # -----------------------------------------------    
    # Download dbc-groups.json file (if it exists) and use device ID to extract relevant DBC list
    def get_device_dbc_list(self,device_id):
        import json 
        
        device_dbc_list = [] 
        fs_dbc_groups_file_path = self.tmp_input_dir / "dbc-groups.json"
        
        try:
            object_found = download_object(self.cloud, self.storage_client, self.bucket_input, "dbc-groups.json", str(fs_dbc_groups_file_path), self.logger)
            if object_found == False:
                self.logger.info("No dbc-groups.json provided - applying all DBC files across all devices")
                return device_dbc_list
            
            # dbc-groups.json exists, so device_id is required
            if device_id == "":
                self.logger.error("dbc-groups.json found but unable to extract device ID from log file path")
                raise RuntimeError("Cannot continue: dbc-groups.json requires valid device ID in log file path")
            
            try:
                with open(fs_dbc_groups_file_path, "r") as file:
                    data = json.load(file)

                for group in data["dbc_groups"]:
                    self.logger.info(f"Evaluating DBC group {group}")
                    if device_id in group["devices"]:
                        device_dbc_list = group["dbc_files"]
                        self.logger.info(f"Device specific DBC files: {device_dbc_list}")
                        break
            except json.JSONDecodeError as e:
                self.logger.error(f"Error parsing dbc-groups.json - invalid JSON format: {e}")
                raise RuntimeError(f"Cannot continue: Invalid JSON in dbc-groups.json - {e}")
        except RuntimeError:
            raise
        except Exception as e:
            self.logger.info(f"Unexpected error processing dbc-groups.json - applying all DBC files across all devices: {e}")
        
        return device_dbc_list
                        
    # -----------------------------------------------
    # Download DBC files
    def download_dbc_files(self, device_dbc_files):
        dbc_files = []
        result = True
        
        for type in ["can", "lin"]:
            try:
                response = list_objects(self.cloud, self.storage_client, self.bucket_input, self.logger, type)
                
                # Process the standardized response format
                for object_info in response["objects"]:
                    dbc_object_name = object_info["name"]
                    if dbc_object_name.endswith(".dbc") and (len(device_dbc_files) == 0 or dbc_object_name in device_dbc_files):
                        local_path = self.tmp_input_dir / dbc_object_name
                        download_object(self.cloud, self.storage_client, self.bucket_input, dbc_object_name, str(local_path), self.logger)
                        dbc_files.append(dbc_object_name)
            except Exception as e:
                self.logger.error(f"Unable to list or download DBC files from {self.bucket_input}:\n {e}")
                result = False
        
        if len(dbc_files) == 0:
            self.logger.error(f"No DBC files with valid prefix in input bucket")
            result = False
        else:
            self.logger.info(f"Downloaded {len(dbc_files)} DBC files with valid prefix from input bucket")
            result = True
        
        return result

    # -----------------------------------------------
    # Download trigger log file
    def download_log_file(self, log_file_object_path):
        from pathlib import Path
        
        # Convert to Path if it's not already
        path_obj = log_file_object_path if isinstance(log_file_object_path, Path) else Path(str(log_file_object_path))
        
        # Create unique filename by replacing separators with underscores
        unique_name = str(path_obj).replace('/', '_').replace('\\', '_')
        
        # Create destination path
        fs_file_path = self.tmp_input_dir / "logfiles" / unique_name
        
        # Download the object
        download_object(self.cloud, self.storage_client, self.bucket_input, str(log_file_object_path), str(fs_file_path), self.logger)

    # -----------------------------------------------   
    # Download passwords.json file if needed
    def download_password_file(self):
        if str(self.log_file_object_path).split(".")[-1] in ["MFE","MFM"]:   
            object_path = "passwords.json"
            fs_file_path = self.tmp_input_dir / object_path
            download_object(self.cloud, self.storage_client, self.bucket_input, object_path, str(fs_file_path), self.logger)
            
    # -----------------------------------------------   
    # Check for and download JSON file if it exists
    def download_json_file(self, object_path):
        import json
        from pathlib import Path

        fs_json_file_path = self.tmp_input_dir / object_path
        Path(fs_json_file_path).parent.mkdir(parents=True, exist_ok=True)
        object_found = download_object(self.cloud, self.storage_client, self.bucket_input, object_path, str(fs_json_file_path), self.logger)

        if object_found == False:
            return []
        
        try:
            with open(fs_json_file_path, 'r') as f:
                json_data = json.load(f)
                return json_data
        except Exception as e:
            self.logger.info(f"{object_path} found in {self.bucket_input}, but the JSON appears invalid: {str(e)}")
            return []
        

# -----------------------------------------------
# DBC decode MDF file to Parquet via MF4 decoder
def decode_log_file(decoder, tmp_input_dir, tmp_output_dir, logger):
    import subprocess, os, shutil
    
    fs_logfiles_path = tmp_input_dir / "logfiles" 
    parquet_files_count = 0
    
    # Check if the logfiles folder contains any files
    logfiles = list(fs_logfiles_path.glob('*.*'))
    if not logfiles:
        logger.error("No log files available for decoding")
        return False
    
    # Handle both absolute and relative paths for the decoder
    if os.path.isabs(decoder):
        shutil.copy(decoder, tmp_input_dir)
    else:
        shutil.copy("./" + decoder, tmp_input_dir)    
    
    subprocess.run([os.path.join(tmp_input_dir, decoder), "-v"], cwd=str(tmp_input_dir),)
    subprocess_result = subprocess.run([os.path.join(tmp_input_dir, decoder),"-i",str(fs_logfiles_path),"-O",str(tmp_output_dir), "--verbosity=1","-X",],cwd=str(tmp_input_dir),)
            
    if subprocess_result.returncode != 0:
        logger.error(f"MF4 decoding failed (returncode {subprocess_result.returncode})")
        result = False 
    else:
        parquet_files_count = len(list(tmp_output_dir.rglob('*.*')))
        logger.info(f"MF4 decoding created {parquet_files_count} Parquet files")
        result = True 

    return result, parquet_files_count

# -----------------------------------------------------------           
# -----------------------------------------------------------
# Class for loading decoded files into a data frame, applying custom processing and store result as Parquet 
class CreateCustomMessages:
    def __init__(self, tmp_output_dir, logger, download_objects=None):
        self.logger = logger
        self.tmp_output_dir =  tmp_output_dir
        self.download_objects = download_objects
    
    def create_custom_messages(self, custom_messages):
        # If no custom-messages.json is found, exit early before importing modules
        if custom_messages == []:
            self.logger.info("No valid custom-messages.json found - skipping this step")
            return 
            
        import pyarrow as pa
        import pyarrow.parquet as pq
        from pathlib import Path
        from .custom_message_functions import apply_custom_function
        
        # List all decoded Parquet files and message paths
        decoded_files = list(self.tmp_output_dir.rglob("*.parquet"))
        all_message_paths = get_all_message_paths(decoded_files)

        # Loop through each custom message
        for idx, custom_message in enumerate(custom_messages, start=1):
            custom_message_name = custom_message["custom_message_name"]
            messages_filtered_list = get_messages_filtered_list(self.tmp_output_dir, custom_message)
            self.logger.info(f"Processing custom message {idx}/{len(custom_messages)}: {custom_message_name}")
            self.logger.info(f"- Input messages: {messages_filtered_list}")
            
            # Loop through each input message per custom message
            for messages_filtered in messages_filtered_list:
                
                # Extract list of related decoded message file paths
                related_message_paths = get_related_message_paths(all_message_paths, messages_filtered)

                if len(related_message_paths) == 0:
                    self.logger.info(f"- No matching decoded files found: {messages_filtered}")
                    continue
                
                # Loop through each unique path per set of related messages
                for (device, date, file_name), messages in related_message_paths.items():           
                
                    # Load message data. If empty, skip
                    df_messages = self.create_df_messages(messages, device, date, file_name, custom_message)     
                    if df_messages.empty:
                        self.logger.info(f"- Decoded file found, but data frame is empty (typically due to short file): {(messages_filtered, device, date, file_name)}")
                        continue 
                    
                    # Update data frame by applying apply custom functions 
                    df_messages = apply_custom_function(df_messages, custom_message["function"], self.download_objects)
                                      
                    # Write the new custom file as Parquet to unique path                     
                    custom_file = self.tmp_output_dir / device / custom_message_name / date / file_name 
                    Path(custom_file).parent.mkdir(parents=True, exist_ok=True)
                    table = pa.Table.from_pandas(df_messages.reset_index())
                    pq.write_table(table, custom_file)  
                    self.logger.info(f"- Wrote custom Parquet file to {custom_file}")               

    # -----------------------------------------------
    # create_custom_messages helper function: Extract input message data 
    def create_df_messages(self, messages, device, date, file_name, custom_message):
        import pandas as pd
        
        dfs = []
        for message in messages:
            decoded_file = self.tmp_output_dir / device / message / date / file_name
            df = load_parquet_to_df(decoded_file, message, custom_message["raster"], custom_message["prefix"])
            df["Message"] = message
            dfs.append(df)
        
        # If resampling is disabled, stack the data (requires identical column names to be meaningful)
        # If resampling is enabled, create a single data frame with all signals in columns 
        if custom_message["raster"] == "":
            df_messages = pd.concat(dfs, axis=0) 
        else:
            df_messages = pd.concat(dfs, axis=1, join="inner")  
        
        return df_messages     

# -----------------------------------------------------------           
# -----------------------------------------------------------
# Class for detecting signal events based on events.json
class DetectEvents:
    def __init__(self, cloud, storage_client, notification_client, bucket_input, tmp_input_dir, tmp_output_dir, logger):
        self.logger = logger
        self.cloud = cloud
        self.storage_client = storage_client
        self.notification_client = notification_client
        self.bucket_input = bucket_input
        self.tmp_input_dir =  tmp_input_dir     
        self.tmp_output_dir =  tmp_output_dir     
    
    def process_events(self, events, device_file):
        # If no events.json is found, exit early before importing modules
        if events == []:
            self.logger.info("No valid events.json found - skipping this step")
            return 
            
        import pyarrow as pa
        import pyarrow.parquet as pq
        from pathlib import Path
        
        # Extract events list and general configuration
        general_cfg = events.get("general", {})
        events_cfg = events.get("events", [])
        
        # If valid device.json file, extract log_meta field
        log_meta = device_file.get("log_meta", "") if isinstance(device_file, dict) else ""
                
        # Get general event info incl. GPS details and SNS body content from the events JSON file
        messages_gps = general_cfg.get("messages_gps", ["CAN9_GnssPos"])
        include_gps_data = general_cfg.get("include_gps_data", True)
        signal_latitude = general_cfg.get("signal_latitude", "Latitude")
        signal_longitude = general_cfg.get("signal_longitude", "Longitude")
        static_body_content = general_cfg.get("static_body_content", "Review details via e.g. your event dashboard") # enables you to add more information to the notification message
        
        # List all decoded Parquet files and message paths
        decoded_files = list(self.tmp_output_dir.rglob("*.parquet"))
        all_message_paths = get_all_message_paths(decoded_files)
        
        # Loop through each event
        for idx, event in enumerate(events_cfg, start=1):
            event_name = event["event_name"]   
            messages_filtered_list = get_messages_filtered_list(self.tmp_output_dir, event)[0]

            self.logger.info(f"Processing event {idx}/{len(events_cfg)}: {event_name}")
            self.logger.info(f"- Input messages: {messages_filtered_list}")
            message_sent = False
                        
            # Loop through each input message per event 
            # Note: The use of [0] forces the script to evaluate lists of messages one-by-one
            for messages_filtered in messages_filtered_list:
                messages_filtered = [messages_filtered]
                
                # Extract list of related decoded message file paths
                related_message_paths = get_related_message_paths(all_message_paths, messages_filtered)
                if len(related_message_paths) == 0:
                    self.logger.info(f"- No matching decoded files found: {messages_filtered}")
                    continue
                                                        
                # Loop through each unique path per set of related messages
                for (device, date, file_name), messages in related_message_paths.items():           
                                        
                    # Load message data. If empty, skip
                    df_messages = self.create_df_messages(messages, device, date, file_name, event, messages_gps, include_gps_data)
                    if df_messages.empty:
                        self.logger.info(f"- Decoded file found, but data frame is empty (typically due to short file): {(messages_filtered, device, date, file_name)}")
                        continue 
                
                    # Loop through each trigger signal for the event
                    for trigger_signal in event["trigger_signals"]:
                        
                        # Test if trigger signal value crosses event thresholds. If so, extract the start/stop event-related subset of data. If empty, skip
                        df_signal_event = self.create_df_signal_event(trigger_signal, event, df_messages)                      
                        if df_signal_event.empty:
                            self.logger.info(f"- No events found: {(messages_filtered, trigger_signal, device, date, file_name)}")
                            pass           
                        else:
                            # Add the event data to the consistent event meta data structure
                            df_signal_event_meta, schema = self.create_df_signal_event_meta(df_signal_event, trigger_signal, event_name, device, messages, include_gps_data, signal_latitude, signal_longitude)
                            
                            # Write the new custom file as Parquet to unique path 
                            custom_file = self.tmp_output_dir / "aggregations" / "events" / date / (device + "_" + messages[0] + "_" + trigger_signal + "_" + event_name + "_"+ file_name)
                            Path(custom_file).parent.mkdir(parents=True, exist_ok=True)
                            table = pa.Table.from_pandas(df_signal_event_meta.reset_index(), schema=schema)
                            pq.write_table(table, custom_file)  
                            self.logger.info(f"- Wrote event Parquet file to {custom_file}")
                            
                            # Upon first identified 'rising edge' event, publish message to SNS topic
                            df_start_events = df_signal_event_meta[df_signal_event_meta["EventValue"] == 1]
     
                            if message_sent == False and df_start_events.empty == False:
                                device_info = f"{device} | {log_meta}" if log_meta else device
                                event_time = df_start_events.index[0].strftime("%Y-%m-%d %H:%M:%S") + " UTC"
                                subject = f"- EVENT: {event_name} | {device_info} | {event_time}"
                                body = f"{event_name} was triggered. {static_body_content}\n\nDetails:\n- device: {device_info}\n- message(s): {messages_filtered}\n- file: {file_name}\n- time: {event_time}"
                                message_sent = self.publish_message(subject, body)
            
    # -----------------------------------------------
    # process_events helper function: Send message to SNS topic for use in event notification
    def publish_message(self, subject, body):
        try:
            result = publish_notification(self.cloud, self.notification_client, subject, body, self.logger)
            return result
        except Exception as e:
            self.logger.error(f"- Error publishing notification: {e}")
            return False
    
    # -----------------------------------------------
    # process_events helper function: Extract event message data frame incl. GPS data
    def create_df_messages(self, messages, device, date, file_name, event, messages_gps, include_gps_data):
        import pandas as pd
        dfs = []
        
        for message in messages:
            decoded_file = self.tmp_output_dir / device / message / date / file_name
            dfs.append(load_parquet_to_df(decoded_file, message, event["raster"]))
        
        # If GPS position data is to be included, try to extract this
        if include_gps_data:
            for gps_message in messages_gps:
                try:
                    decoded_file = self.tmp_output_dir / device / gps_message / date / file_name 
                    dfs.append(load_parquet_to_df(decoded_file, messages[0], event["raster"]))
                    break
                except:
                    pass
        
        # If resampling is disabled, stack the data (requires identical column names to be meaningful)
        # If resampling is enabled, create a single data frame with all signals in columns                       
        if event["raster"] == "":
            df_messages = pd.concat(dfs, axis=0) 
        else:
            df_messages = pd.concat(dfs, axis=1, join="inner") 
        
        return df_messages
                    
    # -----------------------------------------------
    # process_events helper function: Detect trigger signal rising and falling edge events
    def create_df_signal_event(self, trigger_signal, event, df):
        import pandas as pd
        
        if event["exact_match"]:
            df['below_lower'] = df[trigger_signal] == event["lower_threshold"]
            df['above_upper'] = df[trigger_signal] == event["upper_threshold"]
        else:
            df['below_lower'] = df[trigger_signal] <= event["lower_threshold"]
            df['above_upper'] = df[trigger_signal] >= event["upper_threshold"]

        # Track when the signal was last below the lower threshold or above the upper threshold
        df['was_below_lower'] = df['below_lower'].rolling(window=len(df), min_periods=1).max().shift(1, fill_value=0)
        df['was_above_upper'] = df['above_upper'].rolling(window=len(df), min_periods=1).max().shift(1, fill_value=0)

        # Create event groups to detect transitions from below_lower to above_upper or vice versa
        df['event_group_rise'] = (df['below_lower'] != df['below_lower'].shift(1)).cumsum()
        df['event_group_fall'] = (df['above_upper'] != df['above_upper'].shift(1)).cumsum()

        # Identify rising/falling edges in the data
        df_rising = df[df['above_upper'] & (df['was_below_lower'] == 1)].drop_duplicates(subset='event_group_rise', keep='first')
        df_falling = df[df['below_lower'] & (df['was_above_upper'] == 1)].drop_duplicates(subset='event_group_fall', keep='first')
        
        # Depending on the detection logic, assign event start/stop to either rising/falling edges
        if event["rising_as_start"]:
            df_start = df_rising
            df_stop = df_falling
        else:
            df_start = df_falling
            df_stop = df_rising
        
        # Assign meta information
        df_start['EventType'] = 'Start'
        df_start['EventValue'] = 1
        df_stop['EventType'] = 'Stop'
        df_stop['EventValue'] = 0

        # Combine start/stop events, and sort by index
        df_signal_event = pd.concat([df_start, df_stop]).sort_index()
    
        return df_signal_event
    
    # -----------------------------------------------
    # process_events helper function: Create events meta dataframe
    def create_df_signal_event_meta(self, df_signal_event, trigger_signal, event_name, device, messages, include_gps_data, signal_latitude, signal_longitude):
        import pandas as pd
        import pyarrow as pa

        # Create new data frame based on the event data
        df_signal_event_meta = pd.DataFrame()
        df_signal_event_meta.index = df_signal_event.index 
        df_signal_event_meta["EventName"] = event_name
        df_signal_event_meta["DeviceID"] = device 
        df_signal_event_meta["EventId"] = df_signal_event_meta.index.strftime(f"{event_name}_{device}_%Y%m%dT%H%M%S")
        df_signal_event_meta["SignalValue"] = df_signal_event[trigger_signal]
        df_signal_event_meta["EventType"] = df_signal_event["EventType"]
        df_signal_event_meta["EventValue"] = df_signal_event["EventValue"]
        df_signal_event_meta["Message"] = messages[0] 
        df_signal_event_meta["Signal"] = trigger_signal
        
        # If GPS data is to be included, ensure consistent column structure (even if no valid GPS data was extracted)
        if include_gps_data:
            try:
                df_signal_event_meta["Latitude"] = df_signal_event[signal_latitude]
                df_signal_event_meta["Longitude"] = df_signal_event[signal_longitude]
            except:
                df_signal_event_meta["Latitude"] = pd.NA
                df_signal_event_meta["Longitude"] = pd.NA
                                            
        # Define a Parquet schema to ensure correct and consistent type mapping
        schema = pa.schema(
            [
                ("t", pa.timestamp("us")),
                ("EventName", pa.string()),
                ("DeviceID", pa.string()),
                ("EventId", pa.string()),
                ("Message", pa.string()),
                ("Signal", pa.string()),
                ("EventType", pa.string()),
                ("EventValue", pa.int64()),
                ("SignalValue", pa.float64()),
                ("Latitude", pa.float64()),
                ("Longitude", pa.float64())
            ]
        )    
        
        return df_signal_event_meta, schema
    

# -----------------------------------------------------------           
# -----------------------------------------------------------
# Below are useful functions for customizing your Lambda (see CANedge Intro for details)

# -----------------------------------------------
# process_events helper function: Extract messages_filtered_list depending on matching logic for event or custom message data
def get_messages_filtered_list(tmp_output_dir, data):
    if data["messages_match_type"] == "equals":
        messages_filtered_list = data["messages_filtered_list"]
    elif data["messages_match_type"] == "contains":
        messages_filtered_list = [[path.parts[-5] for path in tmp_output_dir.rglob(f'*/*{data["messages_filtered_list"]}*/**/*.parquet') or [None]]]
    elif data["messages_match_type"] == "all_messages":
        messages_filtered_list = [["ALL"]]
    return messages_filtered_list 

# Upload all files in dir to cloud storage
def upload_files_to_cloud(cloud, storage_client, bucket_output, dir):
    from pathlib import Path
    import logging
    import os
    
    logger = logging.getLogger()
    
    # Create list of all local Parquet files and count non-empty folders
    parquet_files = []
    non_empty_folders = 0
    
    for folder in dir.glob("**"):
        if any(folder.glob("*")):
            non_empty_folders += 1
            for file in folder.glob("*.parquet"):
                parquet_files.append(file)
    
    # Upload files to cloud storage
    uploaded_files = 0    
    for file in parquet_files:
        relative_path = str(file.relative_to(dir)).replace(os.sep, '/')
        upload_object(cloud, storage_client, bucket_output, relative_path, str(file), logger)
        uploaded_files += 1
        
    # Print results
    logger.info(f"Uploaded {uploaded_files} Parquet files")
    
    # Return result
    if uploaded_files > 0:
        result = True
    else:
        result = False
        
    return result

# -----------------------------------------------------------
# Load Parquet file to data frame (optionally rename columns for uniqueness, optionally resample)
def load_parquet_to_df(fs_output_file, message, raster="", prefix=False):
    import pyarrow.parquet as pq
    import pandas as pd

    table = pq.read_table(fs_output_file)
    df = table.to_pandas()
    df["t"] = pd.to_datetime(df["t"])
    df.set_index("t", inplace=True)

    if prefix:
        df.columns = [f"{message}_{col}" for col in df.columns]
    
    if raster != "":
        df = df.resample(raster).ffill(limit=1)
        df.index = df.index.round(raster)
        df = df.dropna(how='all')
        
    return df

# -----------------------------------------------------------
# Build a dictionary of all valid paths with key tuples of devices, dates, file_names and messages as values.
def get_all_message_paths(decoded_files):
    all_message_paths = {}
    
    # Iterate over all decoded files, create keys from path components and add messages as values
    for decoded_file in decoded_files:
        p = decoded_file.parts
        device, message, yyyy, mm, dd, file_name = p[-6], p[-5], p[-4], p[-3], p[-2], p[-1]
        date = f"{yyyy}/{mm}/{dd}"
        key = (device, date, file_name)
        
        if key not in all_message_paths:
            all_message_paths[key] = []
        
        all_message_paths[key].append(message)
    
    return all_message_paths

# -----------------------------------------------------------
# Build a dictionary of filtered paths with key tuples of devices, dates, file_names and messages as values.
def get_related_message_paths(all_message_paths, messages_filtered): 
    
    if messages_filtered == ["ALL"]:
        return all_message_paths
    elif len(messages_filtered) > 0:    
        related_message_paths = {
                key: [msg for msg in msgs if msg in messages_filtered]  # Reduce to relevant messages
                for key, msgs in all_message_paths.items()
                if all(msg in msgs for msg in messages_filtered)  # Ensure all filtered messages are present
            }
        return related_message_paths
    else:
        return {}

# -----------------------------------------------------------
# Haversine function to calculate distance in km between two lat/lon points (used in calculated signals example)
def haversine(lat1, lon1, lat2, lon2):
    import math 
        
    lat1_rad, lon1_rad = math.radians(lat1), math.radians(lon1)
    lat2_rad, lon2_rad = math.radians(lat2), math.radians(lon2)
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    a = math.sin(dlat / 2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    distance_in_km = 6371.0 * c
    
    return distance_in_km

# -----------------------------------------------------------
# Function to check if a point is inside any geofence and return the name and ID
def check_geofence(row, signal_latitude, signal_longitude, geofences):
    lat, lon = row[signal_latitude], row[signal_longitude]
    
    for geofence in geofences:
        geofence_id, geofence_name, (geofence_lat, geofence_lon), geofence_radius = geofence
        distance_in_km = haversine(lat, lon, geofence_lat, geofence_lon)
        
        if distance_in_km <= geofence_radius:
            return geofence_id

    return 0 # return 0 if no geofence is matched

# -----------------------------------------------------------           
# -----------------------------------------------------------
# Class for processing backlog.json with flexible prefix specification
class ProcessBacklog:
    def __init__(self, cloud, storage_client, bucket_input, logger, min_batch_size=10, max_batch_size=256):
        self.logger = logger
        self.cloud = cloud
        self.storage_client = storage_client
        self.bucket_input = bucket_input
        self.valid_extensions = [".MF4", ".MFC", ".MFE", ".MFM"]
        self.min_batch_size = min_batch_size
        self.max_batch_size = max_batch_size
        
    def download_backlog_json(self):
        """Download backlog.json from the root of the input bucket/container"""
        import tempfile
        import json
        from pathlib import Path
        
        with tempfile.TemporaryDirectory() as temp:
            tmp_dir = Path(temp)
            backlog_file_path = tmp_dir / "backlog.json"
            
            self.logger.info(f"Downloading backlog.json from {self.cloud} storage: {self.bucket_input}")
            object_found = download_object(self.cloud, self.storage_client, self.bucket_input, "backlog.json", str(backlog_file_path), self.logger)
            
            if not object_found:
                self.logger.error(f"No backlog.json found in the root of the {self.cloud} input {('bucket' if self.cloud != 'Azure' else 'container')}")
                return None
            
            try:
                with open(backlog_file_path, "r") as f:
                    data = json.load(f)
                    
                    # Require the new JSON format with config fields
                    if not isinstance(data, dict):
                        self.logger.error("Invalid backlog.json format: expected an object with 'config' and 'files' properties")
                        return None
                        
                    # Check required fields
                    if "files" not in data:
                        self.logger.error("Invalid backlog.json format: missing 'files' property")
                        return None
                        
                    if "config" not in data:
                        self.logger.error("Invalid backlog.json format: missing 'config' property")
                        return None
                        
                    if "batch_size" not in data["config"]:
                        self.logger.error("Invalid backlog.json format: missing 'batch_size' in config")
                        return None
                        
                    # Get files list
                    backlog_file_data = data["files"]
                    self.logger.info(f"Using backlog.json with {len(backlog_file_data)} items")
                    
                    # Extract batch size parameters from config
                    batch_config = data["config"]["batch_size"]
                    
                    if "min" not in batch_config:
                        self.logger.error("Invalid backlog.json format: missing 'min' in batch_size config")
                        return None
                        
                    if "max" not in batch_config:
                        self.logger.error("Invalid backlog.json format: missing 'max' in batch_size config")
                        return None
                    
                    # Set batch size parameters
                    self.min_batch_size = batch_config["min"]
                    self.max_batch_size = batch_config["max"]
                    self.logger.info(f"Using batch_size parameters from config: min={self.min_batch_size}, max={self.max_batch_size}")
                        
                    return backlog_file_data
            except json.JSONDecodeError as e:
                self.logger.error(f"Error parsing backlog.json - invalid JSON format: {e}")
                return None
            except Exception as e:
                self.logger.error(f"Error reading backlog.json: {e}")
                return None
        
    def has_valid_extension(self, filename):
        """Check if a file has a valid extension"""
        return any(filename.upper().endswith(ext) for ext in self.valid_extensions)
    
    def is_likely_file_path(self, path):
        """Check if a path is likely a file path rather than a prefix"""
        # If it has a valid extension, it's a file
        if self.has_valid_extension(path):
            return True
            
        # Look for patterns that suggest it's a file (has extension part with dot)
        parts = path.split('/')
        last_part = parts[-1] if parts else ""
        # If the last part contains a dot, it's likely a file
        if '.' in last_part:
            return True
            
        return False
    
    def normalize_prefix(self, path):
        """Ensure path ends with a trailing slash if it's a prefix"""
        if not path:
            return path
            
        # Don't add a slash if the path appears to be a file
        if self.is_likely_file_path(path):
            return path
            
        # Only add slash if needed for prefix paths
        if not path.endswith('/'):
            normalized_path = f"{path}/"
            self.logger.info(f"Adding missing trailing slash to prefix: {path} -> {normalized_path}")
            return normalized_path
        return path
        
    def is_device_prefix(self, path):
        """Check if the path is a device prefix (e.g. '0BFD7754/' or '0BFD7754')"""
        import re
        # Normalize path to ensure it has a trailing slash
        normalized_path = self.normalize_prefix(path)
        # Device ID is an 8 character HEX string followed by a slash
        is_device = bool(re.match(r'^[0-9A-F]{8}/$', normalized_path))
        return is_device
    
    def is_session_prefix(self, path):
        """Check if the path is a session prefix (e.g. '0BFD7754/00000001/' or '0BFD7754/00000001')"""
        import re
        # Normalize path to ensure it has a trailing slash
        normalized_path = self.normalize_prefix(path)
        # Session prefix has device ID, followed by 8-digit session number and a slash
        is_session = bool(re.match(r'^[0-9A-F]{8}/[0-9]{8}/$', normalized_path))
        return is_session
    
    def list_sessions(self, device_prefix):
        """List all sessions for a device prefix and return all objects for efficient processing"""
        import re
        
        # Ensure device prefix has trailing slash
        device_prefix = self.normalize_prefix(device_prefix)
        
        sessions = set()
        objects_by_session = {}
        valid_file_count = 0
        
        # Use the pagination-aware listing function from cloud_functions.py
        response = list_objects_with_pagination(self.cloud, self.storage_client, self.bucket_input, self.logger, device_prefix)
        
        # Extract session folders from object paths and organize objects by session
        for obj in response["objects"]:
            name = obj["name"]
            # Match the session folder pattern: deviceid/sessionid/
            match = re.match(f"^{device_prefix}([0-9]{{8}})/", name)
            if match:
                session_prefix = f"{device_prefix}{match.group(1)}/"
                sessions.add(session_prefix)
                
                # Store object by session for later use
                if session_prefix not in objects_by_session:
                    objects_by_session[session_prefix] = []
                
                # Only add files with valid extensions
                if self.has_valid_extension(name):
                    objects_by_session[session_prefix].append(name)
                    valid_file_count += 1
        
        self.logger.info(f"Found {valid_file_count} log files in {device_prefix}")
        return sorted(list(sessions)), objects_by_session
    
    def list_files_in_session(self, session_prefix):
        """List all valid files in a session"""
        # Ensure session prefix has trailing slash
        session_prefix = self.normalize_prefix(session_prefix)
        
        valid_files = []
        # Use the pagination-aware listing function from cloud_functions.py
        response = list_objects_with_pagination(self.cloud, self.storage_client, self.bucket_input, self.logger, session_prefix)
        
        for obj in response["objects"]:
            name = obj["name"]
            if self.has_valid_extension(name):
                valid_files.append(name)
        
        self.logger.info(f"Found {len(valid_files)} log files in {session_prefix}")
        return sorted(valid_files)
    
    def process_backlog_from_cloud(self):
        """Complete workflow to process a backlog.json file from cloud storage"""
        # Download and parse backlog.json - only download once
        backlog_file_data = self.download_backlog_json()
        
        if not backlog_file_data:
            self.logger.error("Failed to load backlog.json - exiting")
            return False
        
        # Prepare batches
        self.logger.info(f"\n\nBACKLOG: PREPARE BATCHES")
        backlog_data_list = [backlog_file_data]
        total_items = len(backlog_file_data)
        self.logger.info(f"Backlog file contains {total_items} items")
        
        # Process the backlog to get batches
        backlog_batches = self.process_backlog(backlog_data_list)
        
        # Optimization: Combine batches from the same device with size constraints
        # This avoids processing small batches separately when it's more efficient to process them together
        # But ensures we don't combine files from different devices or exceed max batch size
        if len(backlog_batches) > 1 and total_items < self.min_batch_size:
            self.logger.info(f"Optimizing by combining small batches from the same device (min_batch_size={self.min_batch_size}, max_batch_size={self.max_batch_size})")
            # Group batches by device ID
            device_batches = {}
            for batch in backlog_batches:
                if not batch:  # Skip empty batches
                    continue
                # Extract device ID from first file in batch (device ID is the first part of the path)
                first_file = batch[0]
                device_id = first_file.split('/')[0] if '/' in first_file else None
                
                if device_id:
                    # Initialize device batch list if needed
                    if device_id not in device_batches:
                        device_batches[device_id] = []
                    # Add all files from this batch to the device batch
                    device_batches[device_id].extend(batch)
                else:
                    # If we can't identify the device, keep the batch separate
                    device_batches[f"unknown_{len(device_batches)}"] = batch
            
            # Now split any device batches that exceed max_batch_size
            final_batches = []
            for device_id, files in device_batches.items():
                # If batch exceeds max size, split it into smaller batches
                if len(files) > self.max_batch_size:
                    self.logger.info(f"Device {device_id} has {len(files)} files, exceeding max_batch_size of {self.max_batch_size}. Splitting into multiple batches.")
                    for i in range(0, len(files), self.max_batch_size):
                        batch_slice = files[i:i + self.max_batch_size]
                        final_batches.append(batch_slice)
                else:
                    final_batches.append(files)
            
            # Replace the original batches with the device-grouped and size-limited batches
            backlog_batches = final_batches
            self.logger.info(f"Optimized into {len(backlog_batches)} device-specific batches with size limits applied")
        
        # Process the MDF batches
        return self.process_mdf_batches(backlog_batches)
    
    def process_mdf_batches(self, backlog_batches):
        """Process MDF batches using mdf_to_parquet"""
        from .mdf_to_parquet import mdf_to_parquet
        
        total_items = sum(len(batch) for batch in backlog_batches)
        self.logger.info(f"Processing {len(backlog_batches)} batches with {total_items} unique objects in total")
        
        # Process each batch
        batch_results = []
        for i, batch in enumerate(backlog_batches, 1):
            self.logger.info(f"\n\n\nBACKLOG: PROCESS BATCH {i} OF {len(backlog_batches)} ({len(batch)} OBJECTS)")
            try:
                # Set up required parameters for mdf_to_parquet
                notification_client = False  # ensures notifications are not sent for events during backlog processing
                bucket_output = f"{self.bucket_input}-parquet"
                
                # For Amazon, initialize notification client
                if self.cloud == "Amazon":
                    import boto3
                    notification_client = boto3.client('sns')
                
                # Call mdf_to_parquet directly
                mdf_to_parquet(self.cloud, self.storage_client, notification_client, batch, self.bucket_input, bucket_output)
                batch_results.append(True)
            except Exception as e:
                self.logger.error(f"Error processing batch {i}: {e}")
                batch_results.append(False)
        
        # Return the combined result (True if all batches succeeded)
        return all(batch_results)
    
    def process_backlog(self, backlog_file_data):
        """Process the backlog data to expand prefixes into individual file paths"""
        import re
        result = []
        processed_sessions = set()  # Track sessions we've already processed
        
        for entry_list in backlog_file_data:
            # Process each item in the list
            session_lists = {}
            
            for original_item in entry_list:
                # Normalize the item once, at the beginning of processing
                item = self.normalize_prefix(original_item) if original_item else original_item
                
                # Now use the normalized item for prefix checking
                if original_item != item:
                    self.logger.info(f"Using normalized prefix: {item}")
                
                # Case 1 (device prefix): List all sessions and process each separately
                if re.match(r'^[0-9A-F]{8}/$', item):
                    sessions, objects_by_session = self.list_sessions(item)
                    
                    # Count total valid files found across all sessions
                    total_valid_files = sum(len(files) for files in objects_by_session.values())
                    self.logger.info(f"Found {len(sessions)} sessions and {total_valid_files} valid files for device {item}")
                    
                    for session in sessions:
                        # Skip if we've already processed this session
                        if session in processed_sessions:
                            self.logger.info(f"Session already processed, skipping: {session}")
                            continue
                            
                        processed_sessions.add(session)
                        self.logger.info(f"Found session: {session}")
                        
                        # Use the objects we already retrieved instead of making another API call
                        files = objects_by_session.get(session, [])
                        if files:
                            session_lists[session] = files

                # Case 2 (session prefix): List all objects
                elif re.match(r'^[0-9A-F]{8}/[0-9]{8}/$', item):
                    # Skip if we've already processed this session
                    if item in processed_sessions:
                        self.logger.info(f"Session already processed, skipping: {item}")
                        continue

                    processed_sessions.add(item)
                    
                    # Check if we already have files for this session from a previous device prefix listing
                    if item in session_lists and session_lists[item]:
                        self.logger.info(f"Using previously listed files for session {item} ({len(session_lists[item])} files)")
                    else:
                        # Only make an API call if we don't already have the files
                        files = self.list_files_in_session(item)
                        if files:
                            session_lists[item] = files

                # Case 3: Individual file: Add directly if it has valid extension
                elif self.has_valid_extension(item):
                    # Extract session path from item
                    parts = item.split('/')
                    if len(parts) >= 3:
                        session_prefix = f"{parts[0]}/{parts[1]}/"

                        # Initialize the session files list if needed
                        if session_prefix not in session_lists:
                            # If we've already processed this session in an earlier list,
                            # initialize with the files we already have
                            if session_prefix in processed_sessions:
                                # This session was processed before, but we still need to add any new files
                                # Find the existing list with this session
                                existing_list = None
                                for list_index, file_list in enumerate(result):
                                    # Check if this list contains files from the same session
                                    if file_list and file_list[0].startswith(session_prefix):
                                        existing_list = list_index
                                        break
                                        
                                if existing_list is not None:
                                    # We found the existing list, initialize with its files
                                    session_lists[session_prefix] = result[existing_list].copy()
                                    # Remove the existing list since we'll replace it
                                    result.pop(existing_list)
                                else:
                                    session_lists[session_prefix] = []
                            else:
                                session_lists[session_prefix] = []
                                
                        # Add file if not already in the list
                        if item not in session_lists[session_prefix]:
                            session_lists[session_prefix].append(item)
                        else:
                            self.logger.info(f"Duplicate file skipped: {item}")
            
            # Mark all sessions as processed
            for session in session_lists:
                processed_sessions.add(session)
                
            # Convert session_lists dictionary to list format
            for session, files in session_lists.items():
                if files:  # Only include non-empty lists
                    # Remove any duplicates before adding
                    unique_files = list(dict.fromkeys(files))  # Preserves order while removing duplicates
                    result.append(unique_files)
        
        return result

#!/usr/bin/env python3
"""
Utility functions for the Fast Monitor Agent.

"""

import logging
import hashlib
import random
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any

# File status constants (matching Django FileStatus choices)
class FileStatus:
    REGISTERED = 'registered'
    PROCESSING = 'processing'
    PROCESSED = 'processed'
    FAILED = 'failed'
    DONE = 'done'


def validate_config(config: dict) -> None:
    """Validate the configuration parameters for message-driven agent."""
    required_keys = [
        "selection_fraction",
    ]

    for key in required_keys:
        if key not in config:
            raise ValueError(f"Missing required configuration key: {key}")

    if not (0.0 <= config["selection_fraction"] <= 1.0):
        raise ValueError("selection_fraction must be between 0.0 and 1.0")






def calculate_checksum(file_path: str, logger: logging.Logger) -> str:
    """
    Calculate MD5 checksum of file.

    Args:
        file_path: Path to the file as string
        logger: Logger instance

    Returns:
        MD5 checksum string
    """
    hash_md5 = hashlib.md5()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except Exception as e:
        logger.error(f"Error calculating checksum for {file_path}: {e}")
        return ""








def simulate_tf_subsamples(stf_file: Dict[str, Any], config: dict, logger: logging.Logger, agent_name: str) -> List[Dict[str, Any]]:
    """
    Simulate creation of Time Frame (TF) subsamples from a Super Time Frame (STF) file.
    
    Args:
        stf_file: STF data dictionary (follows the keys from daq agent)
        config: Configuration dictionary
        logger: Logger instance
        
    Returns:
        List of TF metadata dictionaries
    """
    try:
        tf_files_per_stf = config.get("tf_files_per_stf", 2)
        tf_size_fraction = config.get("tf_size_fraction", 0.15)
        tf_sequence_start = config.get("tf_sequence_start", 1)
        
        tf_subsamples = []
        stf_size = stf_file.get("size_bytes", 0)
        # filename without extension
        base_filename = stf_file.get("filename", "unknown").rsplit('.', 1)[0]
        
        for i in range(tf_files_per_stf):
            sequence_number = tf_sequence_start + i
            
            # Generate TF filename based on STF filename
            tf_filename = f"{base_filename}_tf_{sequence_number:03d}.tf"
            
            # Calculate TF file size as fraction of STF size with some gaussian randomness
            tf_size = int(stf_size * tf_size_fraction * random.gauss(1.0, 0.1))
            
            # Create TF metadata
            tf_metadata = {
                "tf_filename": tf_filename,
                "file_size_bytes": tf_size,
                "sequence_number": sequence_number,
                "stf_parent": stf_file.get("filename"),  # Use unique filename as parent identifier
                "metadata": {
                    "simulation": True,
                    "created_from": stf_file.get('filename'),
                    "tf_size_fraction": tf_size_fraction,
                    "agent_name": agent_name,
                    "state": stf_file.get('state'),
                    "substate": stf_file.get('substate'),
                    "start": stf_file.get('start'),
                    "end": stf_file.get('end'),
                }
            }
            
            tf_subsamples.append(tf_metadata)

        return tf_subsamples

    except Exception as e:
        logger.error(f"Unexpected error simulating TF subsamples: {e}")
        return []


def record_tf_file(tf_metadata: Dict[str, Any], config: dict, agent, logger: logging.Logger) -> Dict[str, Any]:
    """
    Record a Time Frame (TF) file in the database using REST API.
    
    Args:
        tf_metadata: TF metadata dictionary from simulate_tf_subsamples
        config: Configuration dictionary
        agent: BaseAgent instance for API access
        logger: Logger instance
        
    Returns:
        FastMonFile data dictionary or None if failed
    """
    try:
        # Prepare FastMonFile data for API
        tf_file_data = {
            "stf_file": tf_metadata.get("stf_parent", None),  # STF filename as parent identifier
            "tf_filename": tf_metadata["tf_filename"],
            "file_size_bytes": tf_metadata["file_size_bytes"],
            "status": FileStatus.REGISTERED,
            "metadata": tf_metadata.get("metadata", {})
        }
        
        # Create TF file record via FastMonFile API
        tf_file = agent.call_monitor_api('post', '/fastmon-files/', tf_file_data)
        tf_file_id = tf_file.get('tf_file_id') or tf_file.get('id') or 'unknown'
        logger.debug(f"Recorded TF file: {tf_metadata['tf_filename']} -> {tf_file_id}")
        return tf_file
        
    except Exception as e:
        logger.error(f"Error recording TF file {tf_metadata['tf_filename']}: {e}")
        return {}


def create_tf_message(tf_file: Dict[str, Any], stf_file: Dict[str, Any], agent_name: str) -> Dict[str, Any]:
    """
    Create a message for TF file registration notifications.
    
    Args:
        tf_file: TF file data from the FastMonFile API
        stf_file: Parent STF file data
        agent_name: Name of the agent sending the message
        
    Returns:
        Message dictionary ready for broadcasting
    """
    from datetime import datetime
    
    # Extract run number from message data
    run_number = stf_file.get('run_id')
    
    message = {
        "msg_type": "tf_file_registered",
        "processed_by": agent_name,
        "tf_file_id": tf_file.get('tf_file_id'),
        "tf_filename": tf_file.get('tf_filename'),
        "file_size_bytes": tf_file.get('file_size_bytes'),
        "stf_filename": stf_file.get('stf_filename'),
        "run_number": run_number,
        "status": tf_file.get('status'),
        "timestamp": datetime.now().isoformat(),
        "message": f"TF file {tf_file.get('tf_filename')} registered for fast monitoring"
    }
    
    return message


def create_status_message(agent_name: str, status: str, message_text: str, run_id: str = None) -> Dict[str, Any]:
    """
    Create a status message for agent notifications.
    
    Args:
        agent_name: Name of the agent sending the message
        status: Status of the operation (e.g., 'started', 'completed', 'error')
        message_text: Human-readable message describing the status
        run_id: Optional run identifier
        
    Returns:
        Message dictionary ready for broadcasting
    """
    from datetime import datetime
    
    message = {
        "msg_type": "fastmon_status",
        "processed_by": agent_name,
        "status": status,
        "message": message_text,
        "timestamp": datetime.now().isoformat()
    }
    
    if run_id:
        message["run_id"] = run_id
        
    return message

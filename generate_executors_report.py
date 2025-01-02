#!/usr/bin/env python

# This python script reads the settings.json file and the executors_logs.csv file, and then generates a report.

import json
import csv
import re
import time
import datetime
import argparse

app_settings = {}

def matches_pattern(string, pattern):
    return re.search(pattern, string) is not None

# Read the settings.json file and return the content as a JSON object
def read_settings(settingsPath):
    with open(settingsPath) as settings_file:
        return json.load(settings_file)

# Read each row of the CSV file at csvPath and convert to a JSON object
def read_executors_logs(csvPath):
    logs = []
    with open(csvPath) as csvfile:
        csvreader = csv.DictReader(csvfile, skipinitialspace=True)
        for row in csvreader:
            logs.append(row)
    return logs

# Filter and return the logs that the timestamp is between the start and end time, log.Time is the millisecond in String type since epoch
def filter_logs_by_time(logs, start_time, end_time):
    filtered_logs = []

    # if start_time is a string and a valid timestamp yyyy-MM-ddTHH:mm:ss.SSSZ, then convert it to milliseconds since epoch, if conversion fails, then set it to 0
    if isinstance(start_time, str):
        try:
            start_time = int(datetime.datetime.strptime(start_time, "%Y-%m-%dT%H:%M:%S.%fZ").timestamp() * 1000)
        except ValueError:
            start_time = 0
    # else if start_time is a number, then convert it to an integer
    elif isinstance(start_time, (int, float)):
        start_time = int(start_time)
    else:
        start_time = 0
    
    # if end_time is a string and a valid timestamp yyyy-MM-ddTHH:mm:ss.SSSZ, then convert it to milliseconds since epoch, if conversion fails, then set it to the current system time
    if isinstance(end_time, str):
        try:
            end_time = int(datetime.datetime.strptime(end_time, "%Y-%m-%dT%H:%M:%S.%fZ").timestamp() * 1000)
        except ValueError:
            end_time = int(time.time() * 1000)
    # else if end_time is a number, then convert it to an integer
    elif isinstance(end_time, (int, float)):
        end_time = int(end_time)
    else:
        end_time = int(time.time() * 1000)
        
    for log in logs:
        if int(log["Time"]) >= start_time and int(log["Time"]) <= end_time:
            filtered_logs.append(log)

    # Always ensure the logs are sorted by time before returning
    filtered_logs.sort(key=lambda x: int(x["Time"]))

    return filtered_logs

# Filter and return the logs that match all the list of tags
def filter_logs_by_tags(logs, tags):
    # if tags is null, then set tags to an empty list
    if tags is None:
        tags = []
    filtered_logs = []
    for log in logs:
        match = True
        for tag in tags:
            pattern=re.compile(app_settings["tags"][tag]["matchPattern"])
            if not matches_pattern(log[app_settings["tags"][tag]["matchField"]], pattern):
                match = False
                break
        if match:
            filtered_logs.append(log)
    return filtered_logs

# Extract the actual parent of the PR parents which end with /job/PR-xxx, xxx is a build number
def extract_actual_parent(parent):
    pattern=re.compile(r'(.*)/job/PR-\d+')
    match = re.match(pattern, parent)
    if match:
        return match.group(1)
    else:
        return parent
    
# Returns a friendly display text to represent the duration, in x hours y minutes z seconds, x / y / z could be omitted if it is 0
def format_duration(duration):
    hours = duration // 3600000
    minutes = (duration % 3600000) // 60000
    seconds = (duration % 60000) // 1000
    if hours > 0:
        return str(hours) + " hours " + str(minutes) + " minutes " + str(seconds) + " seconds"
    elif minutes > 0:
        return str(minutes) + " minutes " + str(seconds) + " seconds"
    else:
        return str(seconds) + " seconds"

# Returns a friendly display text to represent the cost, in x USD, keep 2 decimal places
def format_cost(cost):
    return str(round(cost, 2)) + " USD"

# Analyze the cost by tag (app_settings["costs"]), store the results in a dictionary costs, returns a sorted list of tags by cost
def analyze_by_cost_tag(logs):
    costs = {}
    for tag in app_settings["costs"]:
        costs[tag] = calculate_cost(logs, tag)
    sorted_tags_by_cost = sorted(costs, key=costs.get, reverse=True)
    return { "sorted_tags": sorted_tags_by_cost, "costs": costs }

# Analyze total duration, cost and build times by parent, store the results in variables parent_duration, parent_cost, parent_build_times, returns an object which contains 3 sorted lists of parent names by duration, cost and build times
def analyze_by_parent(logs):

    parents_duration = {}
    parents_cost = {}
    parents_build_times = {}
    for log in logs:
        # if log.Computer is empty, then continue to the next log
        if log["Computer"] == "":
            continue

        parent = extract_actual_parent(log["Parent"])
        if parent not in parents_duration:
            parents_duration[parent] = 0
        if parent not in parents_cost:
            parents_cost[parent] = 0
        if parent not in parents_build_times:
            parents_build_times[parent] = 0
        parents_duration[parent] += int(log["Duration"])
        parents_cost[parent] += calculate_cost([log], None)
        parents_build_times[parent] += 1
    sorted_parent_names_by_duration = sorted(parents_duration, key=parents_duration.get, reverse=True)
    sorted_parent_names_by_cost = sorted(parents_cost, key=parents_cost.get, reverse=True)
    sorted_parent_names_by_build_times = sorted(parents_build_times, key=parents_build_times.get, reverse=True)
    return {
        "by_duration": { "sorted_names": sorted_parent_names_by_duration, "parents": parents_duration }, 
        "by_cost": { "sorted_names": sorted_parent_names_by_cost, "parents": parents_cost },
        "by_build_times": { "sorted_names": sorted_parent_names_by_build_times, "parents": parents_build_times }
    }

# Calculate the total duration of the logs that match all the list of tags
def calculate_duration(logs, tags):
    # if tags is null, then set tags to an empty list
    if tags is None:
        tags = []

    #if tags is not a list, convert it to a list
    if not isinstance(tags, list):
        tags = [tags]
    
    duration = 0

    for log in logs:
        if log["Computer"] == "":
            continue
        match = True
        for tag in tags:
            if tag not in app_settings["tags"]:
                match = False
                break
            pattern=re.compile(app_settings["tags"][tag]["matchPattern"])
            if not matches_pattern(log[app_settings["tags"][tag]["matchField"]], pattern):
                match = False
                break
        if match:
            duration += int(log["Duration"])

    return duration

# Calculate the total cost of the logs that match the single tag, the hourly cost of this tag is defined in the settings.json file
# So the total cost of a log is the hourly cost of the tag * duration of the log in hours
def calculate_cost(logs, tag):
    totalCost = 0
    # if tag is not null, then get the hourly cost of the tag from the settings.json file
    if tag is None:
        # for each tag in app_settings["costs"], call calculate_cost recursively, and get the total cost
        for tag in app_settings["costs"]:
            totalCost += calculate_cost(logs, tag)
    else:
        hourly_cost = app_settings["costs"][tag]
        if hourly_cost is None:
            return 0
        else:
            duration = calculate_duration(logs, tag)
            totalCost = hourly_cost * duration / 3600000

    return totalCost

# Parses a relative time string and returns the timestamp in milliseconds since epoch
def parse_relative_time(relative_time):
    if relative_time is None:
        return None
    current_time = int(time.time() * 1000)
    if relative_time == "now":
        return current_time
    if relative_time.startswith("-"):
        if relative_time.endswith("s"):
            return current_time - int(relative_time[1:-1]) * 1000
        if relative_time.endswith("m"):
            return current_time - int(relative_time[1:-1]) * 60000
        if relative_time.endswith("h"):
            return current_time - int(relative_time[1:-1]) * 3600000
        if relative_time.endswith("d"):
            return current_time - int(relative_time[1:-1]) * 86400000
    return None

# Parses a time range in string format. If the string contains ":", then the left part is the relative time string of start time and the right part is the relative time string of the end time.
# If not, then the whole string is the relative string of the start time.
# The function returns a tuple of two timestamps in milliseconds since epoch
def parse_time_range(time_range):
    if time_range is None:
        return None, None
    if ":" in time_range:
        start_time, end_time = time_range.split(":")
        return parse_relative_time(start_time), parse_relative_time(end_time)
    else:
        return parse_relative_time(time_range), None

# Converts the time range to a user-friendly string, show the timestamp in local time zone
# if the start time is None, then show text "Earliest"
# if the end time is None, then show text "Now"
# Returns the combined string of start time and end time, connected with " - "
def format_time_range(time_range):
    if time_range[0] is None:
        start_time = "Earliest"
    else:
        start_time = datetime.datetime.fromtimestamp(time_range[0] / 1000).strftime("%Y-%m-%d %H:%M:%S")
    if time_range[1] is None:
        end_time = "Now"
    else:
        end_time = datetime.datetime.fromtimestamp(time_range[1] / 1000).strftime("%Y-%m-%d %H:%M:%S")
    return start_time + " - " + end_time
 
# Check and ensure all the given tags are defined in the settings.json file, if not, print an error message and exit the program
def exit_if_tag_not_defined(tags):
    # if tags is None, then just return
    if tags is None:
        return
    for tag in tags:
        if tag not in app_settings["tags"]:
            print("Error: Tag '" + tag + "' is not defined in the settings.json file")
            exit(1)

# Check and ensure the given input file exists, if not, print an error message and exit the program
def exit_if_input_file_not_exists(input_file):
    import os
    if not os.path.exists(input_file):
        print("Error: Input file '" + input_file + "' does not exist")
        exit(1)

# Check and ensure the given settings file exists, if not, print an error message and exit the program
def exit_if_settings_file_not_exists(settings_file):
    import os
    if not os.path.exists(settings_file):
        print("Error: Settings file '" + settings_file + "' does not exist")
        exit(1)

# Check and ensure all input arguments are valid
def initialize(args):
    exit_if_input_file_not_exists(args.input)
    
    pathToSettings = args.settings
    if pathToSettings is None:
        pathToSettings = "settings.json"
    exit_if_settings_file_not_exists(pathToSettings)
    global app_settings
    app_settings = read_settings(pathToSettings)
    exit_if_tag_not_defined(args.tags.split(",") if args.tags is not None else None)

# Output the execution summary to the console in markdown format
def output_execution_summary(execution_summary):
    print("# Jenkins Execution Report\r\n")
    print("## Input\r\n")
    print("- File: " + execution_summary["input"]["file"])
    print("- Filter by time range: " + format_time_range(execution_summary["input"]["time_range"]) + " (" + str(execution_summary["input"]["logs_after_filter_by_time"]) + "/" + str(execution_summary["input"]["total_logs"]) + " logs)")
    print("- Filter by tags: " + str(execution_summary["input"]["tags"]) + " (" + str(execution_summary["input"]["logs_to_analyze"]) + "/" + str(execution_summary["input"]["logs_after_filter_by_time"]) + " logs)")
    print("\r\n")

    if "result" not in execution_summary:
        print("\r\n**No logs to analyze**")
        return
    
    print("## Analysis\r\n")
    print("### Overall\r\n")
    print("- Earliest Log Time: " + datetime.datetime.fromtimestamp(execution_summary["result"]["earliest_log_time"] / 1000).strftime("%Y-%m-%d %H:%M:%S"))
    print("- Latest Log Time: " + datetime.datetime.fromtimestamp(execution_summary["result"]["latest_log_time"] / 1000).strftime("%Y-%m-%d %H:%M:%S"))
    print("- Total Duration: " + format_duration(execution_summary["result"]["totalDuration"]))
    print("- Total Cost: " + format_cost(execution_summary["result"]["totalCost"]))
    print("\r\n")

    print("### Analysis by Build Duration\r\n")
    # print the sorted parent names by duration, each name starts with a new row, the parent name is the key, the total duration is the value
    for parent_name in execution_summary["result"]["analysis_result_by_parent"]["by_duration"]["sorted_names"]:
        print("- " + parent_name + ": " 
              + format_duration(execution_summary["result"]["analysis_result_by_parent"]["by_duration"]["parents"][parent_name]) + " (" + str(execution_summary["result"]["analysis_result_by_parent"]["by_build_times"]["parents"][parent_name]) + " builds)")

    print("\r\n")
    print("### Analysis by Build Cost\r\n")
    # print the sorted parent names by cost, each name starts with a new row, the parent name is the key, the total cost is the value
    for parent_name in execution_summary["result"]["analysis_result_by_parent"]["by_cost"]["sorted_names"]:
        # print the parent name and the total cost of the parent, if it costs > 0 USD
        if execution_summary["result"]["analysis_result_by_parent"]["by_cost"]["parents"][parent_name] > 1:
            print("- " + parent_name + ": " + format_cost(execution_summary["result"]["analysis_result_by_parent"]["by_cost"]["parents"][parent_name]) + " (" + str(execution_summary["result"]["analysis_result_by_parent"]["by_build_times"]["parents"][parent_name]) + " builds)")

    print("\r\n")
    print("## Analysis by Cost Tags\r\n")
    # print the sorted tags by cost, each tag starts with a new row, the tag is the key, the total cost is the value
    for tag in execution_summary["result"]["analysis_result_by_cost_tag"]["sorted_tags"]:
        print("- " + tag + ": " + format_cost(execution_summary["result"]["analysis_result_by_cost_tag"]["costs"][tag]))

# Run the main function
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate Jenkins Executors Report")
    parser.add_argument("-s", "--settings", type=str, help="Path to the settings.json file")
    parser.add_argument("-t", "--tags", type=str, help="Comma-separated list of tags to filter logs")
    parser.add_argument("-r", "--range", type=str, help="Time range to filter logs, format: start:end")
    parser.add_argument("-i", "--input", type=str, required=True, help="Path to the input CSV file")
    args = parser.parse_args()
    initialize(args)

    execution_summary = {}
    execution_summary["report_time"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    execution_summary["input"] = {}
    execution_summary["input"]["file"] = args.input

    executors_logs = read_executors_logs(args.input)
    execution_summary["input"]["total_logs"] = len(executors_logs)
    time_range = parse_time_range(args.range)

    logs_after_filter_by_time = filter_logs_by_time(executors_logs, time_range[0], time_range[1])
    execution_summary["input"]["time_range"] = time_range
    execution_summary["input"]["logs_after_filter_by_time"] = len(logs_after_filter_by_time)

    logsToAnalyze = filter_logs_by_tags(logs_after_filter_by_time, args.tags.split(",") if args.tags is not None else None)
    execution_summary["input"]["tags"] = args.tags
    execution_summary["input"]["logs_to_analyze"] = len(logsToAnalyze)

    # If logsToAnalyze is not empty, then set the timestamps of the first and the last log to the execution_summary["result"]
    if len(logsToAnalyze) > 0:
        execution_summary["result"] = {}
        execution_summary["result"]["earliest_log_time"] = int(logsToAnalyze[0]["Time"])
        execution_summary["result"]["latest_log_time"] = int(logsToAnalyze[-1]["Time"])
        execution_summary["result"]["totalDuration"] = calculate_duration(logsToAnalyze, None)
        execution_summary["result"]["totalCost"] = calculate_cost(logsToAnalyze, None)
        execution_summary["result"]["analysis_result_by_parent"] = analyze_by_parent(logsToAnalyze)
        execution_summary["result"]["analysis_result_by_cost_tag"] = analyze_by_cost_tag(logsToAnalyze)
    
    output_execution_summary(execution_summary)
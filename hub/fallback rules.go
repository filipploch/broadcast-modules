package main

// fallbackRules defines all fallback write rules.
// DBPath is NOT specified here — it is set dynamically when main_module registers.
// Add new rules here when you want HUB to persist critical data
// to SQLite when main_module is offline.
func fallbackRules() []FallbackRule {
	return []FallbackRule{
		{
			// When obs-ws-plugin reports recording started,
			// save the output filename to settings.obs_record_filepath.
			FromModule: "obs-ws-plugin",
			MsgType:    "obs_event",
			MatchFunc: func(msg *Message) bool {
				eventType := getNestedString(msg.Payload, "eventType")
				outputState := getNestedString(msg.Payload, "eventData.outputState")
				return eventType == "RecordStateChanged" &&
					outputState == "OBS_WEBSOCKET_OUTPUT_STARTED"
			},
			ValueFunc: func(msg *Message) (table, column, whereCol, whereVal, value string) {
				outputPath := getNestedString(msg.Payload, "eventData.outputPath")
				// UPDATE settings SET obs_record_filepath = ? WHERE id = 1
				return "settings", "obs_record_filepath", "id", "1", outputPath
			},
		},

		// Add more rules here as needed, e.g.:
		//
		// {
		//     FromModule: "obs-ws-plugin",
		//     MsgType:    "obs_event",
		//     MatchFunc: func(msg *Message) bool {
		//         eventType := getNestedString(msg.Payload, "eventType")
		//         outputState := getNestedString(msg.Payload, "eventData.outputState")
		//         return eventType == "RecordStateChanged" &&
		//             outputState == "OBS_WEBSOCKET_OUTPUT_STOPPED"
		//     },
		//     ValueFunc: func(msg *Message) (table, column, whereCol, whereVal, value string) {
		//         return "settings", "obs_record_filepath", "id", "1", ""
		//     },
		// },
	}
}

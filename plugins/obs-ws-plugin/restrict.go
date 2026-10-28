package main

// requestAllowed: czy plugin może przekazać do OBS żądanie o danej nazwie. Bez listy allowed_requests (domyślnie) wolno wszystko;
// z listą wolno tylko dokładnie wymienione nazwy (także puste requestType jest wtedy odrzucane).
func (c *Config) requestAllowed(requestType string) bool {
	if len(c.AllowedRequests) == 0 {
		return true
	}
	for _, a := range c.AllowedRequests {
		if a == requestType {
			return true
		}
	}
	return false
}

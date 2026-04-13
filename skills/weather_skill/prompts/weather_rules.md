## Weather Skill

You have access to weather information tools.

### Available Tools

1. **get_weather** - Get current weather for a city
   - Parameters: `city` (string), `units` (optional: "metric" or "imperial")

2. **get_forecast** - Get weather forecast for a city
   - Parameters: `city` (string), `days` (optional: number of days), `units` (optional)

### Usage Guidelines

- Always confirm the city name with the user if ambiguous
- Default to metric units unless user specifies otherwise
- For forecast requests, ask how many days if not specified
- If weather data is unavailable, explain this to the user

## Overview

This project is a simple Natural Language Understanding (NLU) system combined with a weather metric API.  
You can type a natural language question such as: 

What is the weather in Chennai and Madurai now?


The system extracts:
- the metric (for example: temperature),
- the location (can be one or multiple places),
- and the time expression (for example: now or today),

and then queries the OpenWeather API to return actual weather values.

A minimal frontend (`nlu_frontend.html`) is included and is served by the FastAPI backend directly at the root URL.


## Features

- Extracts common weather-related metrics (temperature, humidity, rainfall, wind speed, pressure).
- Treats the word “weather” as temperature.
- Detects simple time expressions (now, today, yesterday, months).
- Extracts locations of the form “in <location>”.
- Splits and cleans multiple locations such as “Chennai and Madurai”.
- Calls OpenWeatherMap for real-time weather values.
- Frontend and backend are served together, avoiding CORS issues.

---

## Requirements

Install all dependencies:

```

pip install -r requirements.txt

```

---

## Environment Variables

Create a `.env` file in the project root and add your OpenWeather API key:

```

OWM_API_KEY=your_key_here

```

Alternative supported key:

```

OWA=your_key_here

```

At least one of these must be set.

---

## Running the Application

Start the backend server:

```

uvicorn nlu_main:app --reload --host 127.0.0.1 --port 8000

```

Open your browser:

```

[http://localhost:8000/](http://localhost:8000/)

````

You will see the frontend where you can type natural language queries.

---

## API Endpoints

### 1. Extract Metric  
`POST /extract_metric`

Example request body:

```json
{
  "text": "What is the temperature in Chennai now?"
}
````

### 2. Get Metric

`GET /get_metric?metric=temperature&location=chennai`

Supports multiple locations:

```
/get_metric?metric=temperature&location=chennai and madurai
```

---

## Project Structure

```
project/
│
├── nlu_main.py
├── nlu_frontend.html
├── requirements.txt
├── .env
└── README.md
```

---

## Notes for Developers

* The NLU is rule-based and simple.
* Location extraction relies on the phrase “in <location>”.
* Sanitization removes time words from location strings.
* The frontend communicates with the backend using basic fetch requests.

---

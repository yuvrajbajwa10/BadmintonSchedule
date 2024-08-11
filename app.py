from flask import Flask, request, render_template, jsonify
import requests
from datetime import datetime, timedelta
import sqlite3
import json
import logging
from logging.handlers import RotatingFileHandler
import pytz
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
import os

logging.info('Starting app...')
app = Flask(__name__)
if not os.path.exists('./data'):
    os.makedirs('./data')

if not os.path.exists('/tmp/booking'):
    os.makedirs('/tmp/booking')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[RotatingFileHandler('/tmp/booking/app.log', maxBytes=3000000, backupCount=4),
                              logging.StreamHandler()])

dbPathString = './data/bookings.db'
def init_db():
    conn = sqlite3.connect(dbPathString)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS bookings
                 (date TEXT, sport_court TEXT, data JSON)''')
    # create table called config a singleton row to store a column called last_updated to store the last time the data was fetched
    c.execute('''CREATE TABLE IF NOT EXISTS config
                 (last_updated TEXT)''')
    conn.commit()
    conn.close()

# Initialize global session
session = None
cookie = None

def create_session():
    global session
    session = requests.Session()
    session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    })
    session.headers.update({
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br',
    "Accept": "*/*",
    "Accept-Language": "en-GB,en;q=0.9,en-US;q=0.8",
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Origin": "https://internetbookings.net.nz",
    "Referer": "https://internetbookings.net.nz/smii/",
    "User-Agent": "Mozilla/5.0"
    })
    retries = Retry(total=5, backoff_factor=1, status_forcelist=[502, 503, 504])
    session.mount('https://', HTTPAdapter(max_retries=retries))

def is_session_valid():
    global session
    if session is None:
        return False
    try:
        response = session.get("https://internetbookings.net.nz/smii/php/ajax.php", timeout=5)
        return response.status_code == 200
    except requests.RequestException:
        return False

def get_cookie():
    global session
    if not is_session_valid():
        logging.info("Session invalid or expired. Creating a new session.")
        create_session()

    reqUrl = "https://internetbookings.net.nz/smii/php/ajax.php"
    headersList = {
        "Accept": "*/*",
        "Accept-Language": "en-GB,en;q=0.9,en-US;q=0.8",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": "https://internetbookings.net.nz",
        "Referer": "https://internetbookings.net.nz/smii/",
        "User-Agent": "Mozilla/5.0"
    }
    payload = "start_club=&login=1&function=login&user=" + user + "&pass=" + password
    try:
        response = session.post(reqUrl, data=payload, headers=headersList)
        response.raise_for_status()

        logging.info(f"Login response status code: {response.status_code}")
        logging.info(f"Login response cookies: {dict(session.cookies)}")

        if 'PHPSESSID' not in session.cookies:
            logging.error("PHPSESSID not found in response cookies")
            return None

        return session.cookies

    except requests.RequestException as e:
        logging.error(f"Error in get_cookie(): {str(e)}")
        return None

def is_valid_cookie(cookie):
    if cookie is None:
        return False
    
    for key, value in cookie.items():
        if hasattr(value, 'expires'):
            if isinstance(value.expires, datetime):
                if value.expires < datetime.now():
                    return False
            elif isinstance(value.expires, (int, float)):
                if value.expires < datetime.now().timestamp():
                    return False
        else:
            continue
    
    return True

def fetch_booking_data(date, sport_court, manual_cookie=None):
    global cookie

    if manual_cookie:
        cookie_str = manual_cookie
        logging.info('Using manually provided cookie')
    else:
        return None

    cookie_str = f"PHPSESSID={manual_cookie}"
    logging.info(f'Fetching data for {date} and court {sport_court}...')
    reqUrl = "https://internetbookings.net.nz/smii/php/ajax.php"
    
    headersList = {
        "Accept": "*/*",
        "Accept-Language": "en-GB,en;q=0.9,en-US;q=0.8",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Cookie": cookie_str,
        "Origin": "https://internetbookings.net.nz",
        "Pragma": "no-cache",
        "Referer": "https://internetbookings.net.nz/smii/main",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36 Edg/127.0.0.0",
        "X-Requested-With": "XMLHttpRequest",
        "sec-ch-ua": '"Not)A;Brand";v="99", "Microsoft Edge";v="127", "Chromium";v="127"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"'
    }

    payload = f"function=booking_sheet&cal_view=0&source=0&bookings=&width=&sport_court={sport_court}&date={date.strftime('%Y+%m+%d')}"

    try:
        response = requests.request("POST", reqUrl, data=payload, headers=headersList)
        response.raise_for_status()  # Raises an HTTPError for bad responses
        
        content = response.text.strip()
        logging.info(f"Response status code: {response.status_code}")
        logging.info(f"Length of response: {len(content)}")
        
        if not content:
            logging.error(f'No data received for {date} and court {sport_court}')
            return None
        
        logging.debug(f"Response content: {content[:200]}...")  # Log first 200 characters of response
        
        try:
            return response.json()
        except ValueError as json_error:
            logging.error(f"Failed to parse JSON: {str(json_error)}")
            logging.debug(f"Raw response: {content}")
            return None
    
    except requests.RequestException as e:
        logging.error(f'Failed to fetch data for {date} and court {sport_court}: {str(e)}')
        return None
def fetch_and_store_data(cookie_string):
    logging.info('Fetching and storing data...')
    conn = sqlite3.connect(dbPathString)
    dataUpdated = False
    c = conn.cursor()
    start_date = datetime.now() 
    auckland_time = pytz.timezone('Pacific/Auckland')
    auckland_now = datetime.now(auckland_time)
    if auckland_now.hour >= 21:
        start_date += timedelta(days=1)
    for i in range(10):
        date = start_date + timedelta(days=i)
        for court in ['A', 'B', 'D']:
            data = fetch_booking_data(date, court, cookie_string)
            if not data:
                continue
            dataUpdated = True
            c.execute("INSERT OR REPLACE INTO bookings (date, sport_court, data) VALUES (?, ?, ?)",
                      (date.strftime("%Y-%m-%d"), court, json.dumps(data)))

    conn.commit()
    conn.close()
    return dataUpdated

@app.route('/fetchandstore', methods=['POST'])
def fetch_and_store():
    cookie_string = request.form.get('cookie-string')
    logging.info(f'Cookie string: {cookie_string}')
    dataUpdated = fetch_and_store_data(cookie_string)
    if dataUpdated:
        # Update last_updated in config table
        conn = sqlite3.connect(dbPathString)
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO config (last_updated) VALUES (?)", (datetime.now().strftime('%Y-%m-%d %H:%M:%S'),))
        conn.commit()
        conn.close()
    if dataUpdated:
        return 'Data fetched and stored!'
    
    return 'Data Update Failed!'

def get_last_updated():
    conn = sqlite3.connect(dbPathString)
    c = conn.cursor()
    c.execute("SELECT last_updated FROM config")
    last_updated = c.fetchone()
    conn.close()
    if last_updated:
        return last_updated[0]
    return 'Never'

@app.route('/')
def index():
    return render_template('index.html', last_updated=get_last_updated())

@app.route('/open-modal')
def open_modal():
    return render_template('modal.html')

@app.route('/filter', methods=['POST'])
def filter_courts():
    logging.info('Filtering courts...')
    start_time = request.form.get('start_time')
    end_time = request.form.get('end_time')
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')

    conn = sqlite3.connect(dbPathString)
    c = conn.cursor()

    available_courts = {}

    logging.info(f'Filtering courts from {start_date} to {end_date} between {start_time} and {end_time}...')
    c.execute("SELECT date, sport_court, data FROM bookings WHERE date BETWEEN ? AND ?", (start_date, end_date))
    results = c.fetchall()

    for result in results:
        date, court, data = result
        data = json.loads(data)
        bookings_data = data['bookings_data']

        available_times = []
        for row in bookings_data['rows']:
            rowTime = row['time']
            if rowTime == "0:00am":
                rowTime = "12:00am"
            if rowTime == "0:30am":
                rowTime = "12:30am"

            time_time = datetime.strptime(rowTime, '%I:%M%p')
            start_time_time = datetime.strptime(start_time, '%H:%M')
            end_time_time = datetime.strptime(end_time, '%H:%M')

            if start_time_time <= time_time <= end_time_time:
                cell_datas = row['cell_data']
                for courtNumber, cell_data in cell_datas.items():
                    if "title" in cell_data and cell_data["title"] in ["Peak", ""]:
                        available_times.append((rowTime, courtNumber))

        if available_times:
            court_schedule = {}
            for time, courtNumber in available_times:
                if courtNumber not in court_schedule:
                    court_schedule[courtNumber] = []
                court_schedule[courtNumber].append(time)

            filtered_courts = []
            for courtNumber, times in court_schedule.items():
                filtered_times = get_filtered_times(times)
                if filtered_times:
                    filtered_courts.append({courtNumber: filtered_times})

            if date not in available_courts:
                available_courts[date] = {}
            # sort filtered_courts by number of available times
            filtered_courts.sort(key=lambda x: len(list(x.values())[0]), reverse=True)

            available_courts[date][court] = filtered_courts[:5]

    conn.close()
    return render_template('available_courts.html', available_courts=available_courts)


def convert_to_datetime(time_str):
    # Convert time string to datetime object
    return datetime.strptime(time_str, '%I:%M%p')


from datetime import datetime, timedelta


def get_filtered_times(times):
    filtered_times = []
    if not times:
        return filtered_times

    times_as_dt = [convert_to_datetime(t) for t in times]

    previous_time = times_as_dt[0]
    for i in range(len(times_as_dt)):
        current_time = times_as_dt[i]
        time_diff = current_time - previous_time

        if time_diff >= timedelta(hours=1):
            thisTime = datetime.strftime(previous_time, '%I:%M %p')
            filtered_times.append(f"{thisTime} (1hr)")
            previous_time = current_time

    # Add the last time if it hasn't been added
    if filtered_times and previous_time != times_as_dt[-1]:
        lastTime = datetime.strftime(previous_time, '%I:%M %p')
        filtered_times.append(f"{lastTime} (1hr)")

    return filtered_times


@app.template_filter('format_date')
def format_date(date_str):
    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        return date_obj.strftime('%A, %d/%m/%Y')
    except ValueError:
        return 'Invalid date'


@app.template_filter('correct_court_name')
def correct_court_name(number, type):
    # parse the number from a str 
    court = int(number)
    if type == 'A':
        return f'{court}'
    elif type == 'B':
        return f'{court + 9}'
    elif type == 'D':
        return f'{court + 16}'
    else:
        return 'Invalid court'


if __name__ == '__main__':
    logging.info('Starting app...')
    init_db()
    app.run(debug=True)
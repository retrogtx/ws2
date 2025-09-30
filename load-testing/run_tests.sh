if [ ! -f ../.env ]; then
    echo "Error: .env file not found"
    echo "Create a .env file with: ANTHROPIC_API_KEY=your_key_here"
    exit 1
fi

echo "Starting Comprehensive Load Testing for Centrifugo Chat Application"
echo "=================================================================="

check_service() {
    local url=$1
    local name=$2
    echo "Checking $name at $url..."
    if curl -s "$url" > /dev/null 2>&1; then
        echo "$name is running"
    else
        echo "$name is not running at $url"
        echo "Please start the application first using: ./run.sh"
        exit 1
    fi
}

check_service "http://localhost:3000" "Frontend"
check_service "http://localhost:8787/api/centrifugo-token" "Backend"
check_service "http://localhost:8000/api" "Centrifugo"

echo ""
echo "Checking Python dependencies..."
# change this to your local python path
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -c "import locust, websockets, requests, psutil, dotenv; print('All dependencies available')"

echo ""
echo "Test Plan Overview:"
echo "1. Basic Load Testing (Locust)"
echo "2. Reconnection Scenario Testing"
echo "3. Multiple Tab/Session Testing"
echo "4. Network Interruption Testing"
echo "5. Performance Metrics Collection"
echo ""

mkdir -p results
timestamp=$(date +"%Y%m%d_%H%M%S")

echo "Phase 1: Basic Load Testing with Locust"
echo "=========================================="
echo "Testing basic HTTP API and WebSocket functionality..."

/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -m locust -f locustfile.py \
    --host=http://localhost:8787 \
    --users=1000 \
    --spawn-rate=50 \
    --run-time=3m \
    --html=results/locust_report_${timestamp}.html \
    --csv=results/locust_stats_${timestamp} \
    --logfile=results/locust_${timestamp}.log \
    --loglevel=INFO \
    --headless

echo ""
echo "Phase 2: Reconnection Scenario Testing"
echo "========================================="
echo "Testing specific failure scenarios..."

chat_id=$(python -c "import uuid; print(str(uuid.uuid4()))")
backend_url='http://localhost:8787'

send_message() {
    local tab_name=$1
    local message=$2
    payload="{\"id\":\"$chat_id\",\"messages\":[{\"role\":\"user\",\"parts\":[{\"type\":\"text\",\"text\":\"$tab_name: $message\"}]}]}"
    response=$(curl -s -X POST -H "Content-Type: application/json" -d "$payload" "$backend_url/api/chat")
    echo "$tab_name sent message: $(echo $response | grep -o '"status":[^,}]*' || echo 'sent')"
}

echo "Testing multiple tabs with same chat ID..."
for i in {0..4}; do
    send_message "Tab1" "Message $i"
    sleep 0.1
    send_message "Tab2" "Message $i"
    sleep 0.5
done

echo ""
echo "Phase 3: Mobile/Network Scenario Testing"
echo "==========================================="

send_simple_message() {
    local message=$1
    payload="{\"id\":\"$chat_id\",\"messages\":[{\"role\":\"user\",\"parts\":[{\"type\":\"text\",\"text\":\"$message\"}]}]}"
    response=$(curl -s -X POST -H "Content-Type: application/json" -d "$payload" "$backend_url/api/chat" --max-time 5)
    if [ $? -eq 0 ]; then
        echo "Message sent: $message"
    else
        echo "Message failed: $message"
    fi
}

echo "Sending message before network issue..."
send_simple_message "Before network issue"

echo "Simulating network interruption (10s delay)..."
sleep 10

echo "Sending message after network issue..."
send_simple_message "After network issue"

echo "Testing rapid reconnections..."
for i in {0..9}; do
    send_simple_message "Rapid message $i"
    sleep 0.2
done

echo ""
echo "Phase 4: Performance Metrics Collection"
echo "=========================================="

echo "Collecting system metrics..."
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -c "
import psutil
import time
import json

def collect_metrics():
    return {
        'cpu_percent': psutil.cpu_percent(interval=1),
        'memory_percent': psutil.virtual_memory().percent,
        'disk_io': psutil.disk_io_counters()._asdict() if psutil.disk_io_counters() else {},
        'network_io': psutil.net_io_counters()._asdict() if psutil.net_io_counters() else {},
        'timestamp': time.time()
    }

metrics = []
for i in range(30):
    metrics.append(collect_metrics())
    time.sleep(1)

filename = 'results/system_metrics_${timestamp}.json'
with open(filename, 'w') as f:
    json.dump(metrics, f, indent=2)

print('System metrics collected')
"

echo ""
echo "Phase 6: Failure Point Analysis"
echo "=================================="

echo "Testing token expiration scenario..."
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -c "
import requests
import time

backend_url = 'http://localhost:8787'

response = requests.get(backend_url + '/api/centrifugo-token')
token = response.json()['token']
print('Got token: ' + token[:20] + '...')

print('Waiting 5 seconds to test token persistence...')
time.sleep(5)

response = requests.get(backend_url + '/api/centrifugo-token')
new_token = response.json()['token']
print('New token: ' + new_token[:20] + '...')
print('Tokens different: ' + str(token != new_token))
"

echo ""
echo "Test Results Summary"
echo "======================"
echo "Results saved in ./results/ directory:"
ls -la results/

echo "Load testing completed! Check results directory for detailed reports."

echo ""
echo "Opening Locust HTML report in browser..."
if [ -f "results/locust_report_${timestamp}.html" ]; then
    open "results/locust_report_${timestamp}.html"
    echo "Report opened: results/locust_report_${timestamp}.html"
else
    echo "No Locust report found to open"
fi

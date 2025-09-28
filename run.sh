if [ ! -f .env ]; then
    echo "Error: .env file not found"
    echo "Create a .env file with: ANTHROPIC_API_KEY=your_key_here"
    exit 1
fi

echo "Starting all services with .env file..."
echo "Frontend: http://localhost:3000"
echo "Backend: http://localhost:8787"
echo "Centrifugo: http://localhost:8000"
echo ""
echo "Press Ctrl+C to stop"

docker run --rm \
    -p 3000:3000 \
    -p 8787:8787 \
    -p 8000:8000 \
    -p 6379:6379 \
    --env-file .env \
    ws2

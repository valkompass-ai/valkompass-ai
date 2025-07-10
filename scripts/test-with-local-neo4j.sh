#!/bin/bash

# Script to run tests with a local Neo4j instance (for development)
# This mimics what the GitHub Actions workflow does

set -e

echo "🚀 Starting local Neo4j test environment setup..."

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker first."
    exit 1
fi

# Check if Neo4j container exists and remove it if it does
if docker ps -a --format 'table {{.Names}}' | grep -q 'test-neo4j'; then
    echo "🧹 Removing existing test Neo4j container..."
    docker rm -f test-neo4j > /dev/null 2>&1 || true
fi

# Start Neo4j in Docker
echo "🐳 Starting Neo4j container..."
docker run -d \
    --name test-neo4j \
    --publish 7687:7687 \
    --publish 7474:7474 \
    --env NEO4J_AUTH=neo4j/test-password \
    --env NEO4J_PLUGINS='["graph-data-science"]' \
    --env NEO4J_dbms_security_procedures_unrestricted='gds.*,apoc.*' \
    --env NEO4J_dbms_security_procedures_allowlist='gds.*,apoc.*' \
    neo4j:5.28-community

# Wait for Neo4j to be ready
echo "⏳ Waiting for Neo4j to be ready..."
for i in {1..30}; do
    if docker exec test-neo4j cypher-shell -u neo4j -p test-password "RETURN 1" >/dev/null 2>&1; then
        echo "✅ Neo4j is ready!"
        break
    fi
    echo "   Attempt $i/30: Neo4j not ready yet, waiting 5 seconds..."
    sleep 5
done

# Check if Neo4j is ready
if ! docker exec test-neo4j cypher-shell -u neo4j -p test-password "RETURN 1" >/dev/null 2>&1; then
    echo "❌ Neo4j failed to start properly"
    docker logs test-neo4j
    exit 1
fi

# Set environment variables for testing
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USERNAME=neo4j
export NEO4J_PASSWORD=test-password
export APP_DOMAIN=http://localhost:3000

# Check if .env.test exists, if not create a basic one
if [ ! -f .env.test ]; then
    echo "📝 Creating .env.test file..."
    cat > .env.test << EOF
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=test-password
APP_DOMAIN=http://localhost:3000
# Add your API keys here:
# OPENAI_API_KEY=your_openai_key_here
# GEMINI_API_KEY=your_gemini_key_here
EOF
    echo "⚠️  Please add your API keys to .env.test and run this script again"
    docker rm -f test-neo4j
    exit 1
fi

# Source the test environment
if [ -f .env.test ]; then
    export $(cat .env.test | grep -v '^#' | xargs)
fi

# Check if required API keys are set
if [ -z "$OPENAI_API_KEY" ] || [ -z "$GEMINI_API_KEY" ]; then
    echo "❌ Required API keys not found in .env.test"
    echo "   Please set OPENAI_API_KEY and GEMINI_API_KEY in .env.test"
    docker rm -f test-neo4j
    exit 1
fi

echo "📦 Installing dependencies..."
bun install --frozen-lockfile

echo "🐍 Setting up Python knowledge base environment..."
cd knowledge-base
uv sync
cd ..

echo "📄 Processing knowledge base documents..."
cd knowledge-base

echo "   Parsing documents..."
uv run python main.py --actions parse

echo "   Generating embeddings..."
uv run python main.py --actions embed

echo "   Creating topic models..."
uv run python main.py --actions topicmodel

echo "   Populating graph database..."
uv run python main.py --actions graph

cd ..

# Verify database population
echo "🔍 Verifying database population..."
DOCS=$(docker exec test-neo4j cypher-shell -u neo4j -p test-password "MATCH (d:Document) RETURN count(d) as count" --format plain | tail -1)
SEGMENTS=$(docker exec test-neo4j cypher-shell -u neo4j -p test-password "MATCH (s:DocumentSegment) RETURN count(s) as count" --format plain | tail -1)
TOPICS=$(docker exec test-neo4j cypher-shell -u neo4j -p test-password "MATCH (t:Topic) RETURN count(t) as count" --format plain | tail -1)

echo "   Documents: $DOCS"
echo "   Segments: $SEGMENTS"
echo "   Topics: $TOPICS"

if [ "$DOCS" -eq "0" ] || [ "$SEGMENTS" -eq "0" ]; then
    echo "❌ Database population failed"
    docker rm -f test-neo4j
    exit 1
fi

echo "✅ Database successfully populated!"

echo "🧪 Running knowledge base tests..."
cd knowledge-base
uv run pytest -v
cd ..

echo "🧪 Running frontend linting..."
bun run lint

echo "🧪 Running frontend integration tests..."
bun run test:run

echo "🏗️  Building application..."
bun run build

echo "🧹 Cleaning up..."
docker rm -f test-neo4j

echo "✅ All tests completed successfully!"
echo ""
echo "💡 To run this setup again:"
echo "   ./scripts/test-with-local-neo4j.sh"
echo ""
echo "💡 To keep Neo4j running for development:"
echo "   Comment out the 'docker rm -f test-neo4j' line at the end of this script"
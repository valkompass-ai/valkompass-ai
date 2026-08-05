![Valkompass Logo](images/valkompass_image.avif)

# Welcome to Valkompass!

Valkompass.ai is an open-source tool that helps you explore and compare the positions and decisions of Swedish political parties. By collecting official documents—such as party programs, election manifestos, voting records, parliamentary reports, and other public protocols—Valkompass.ai leverages advanced AI (OpenAI GPT-5.6 Luna) to analyze this information. You can ask questions and engage in conversations, with answers grounded in the actual stances and actions of the parties.

Whether you're a voter seeking clarity, a journalist researching policy, or simply curious about Swedish politics, Valkompass.ai empowers you to make informed decisions with transparent, data-driven insights.

## History
Valkompass.ai was created during a hackathon at Mashup Day Malmö in May 2025.

## Tech Stack

- **Frontend**: Next.js, TypeScript, React
- **AI**: OpenAI GPT-5.6 Luna for analysis, OpenAI embeddings for retrieval
- **Database**: Neo4j for knowledge graph storage
- **Package Manager**: Bun for frontend, UV for Python
- **Knowledge Processing**: Python for document parsing and analysis

## Prerequisites

- Node.js 20+ or Bun
- Python 3.13+ (for knowledge base processing)
- Neo4j database (optional for local development), docker compose available.

## Getting Started

First, run the development server:

```bash
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.


## How do we handle political data? 

All raw and processed data points are stored in the [knowledge-base](./knowledge-base/) directory. Whenever we deploy a new version of valkompass.ai, only the data available in [structured-knowledge-base](./knowledge-base/structured-knowledge-base/) is transferred to our Neo4j database. This process enhances transparency regarding the data the AI can access.

## Contributing

We welcome contributions! Here's how to get started:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests and ensure code quality
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to your branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

### Areas where we need help:
- Adding more political data sources.
- Improving AI analysis accuracy
- Frontend UI/UX improvements
- Documentation
- Testing and bug fixes
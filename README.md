# Fabrice — Vallée's UFO Catalog

A searchable, cross-referenced wiki of UFO close encounter cases and anomalies drawn from the works of Jacques Vallée. This project uses [Quartz](https://quartz.jzhao.xyz/) as its publishing engine to organize over 1,450 cases spanning from Antiquity to the modern era.

🔗 **Live Site:** [https://kirk-iliev.github.io/fabrice](https://kirk-iliev.github.io/fabrice)

## About

This project digitizes and structures the vast catalogs of unexplained aerial phenomena collected by Jacques Vallée and his collaborators. While it currently heavily features cases from *Passport to Magonia* (1969) and *Wonders in the Sky* (2010), it is intended to grow into a generalized dataset representing his extensive research.

### Features

- **Searchable Index:** Quick access to a rapidly growing database of cases.
- **Categorization:** Cases are tagged by classification (CE1, CE2, CE3), phenomena (humanoid, trace-evidence), and exact geographic locations.
- **Geographic & Chronological Linking:** Quartz backlinks and tags connect cases sharing locations or timeframes.

## Project Structure

- `content/`: The Markdown files for each case and site pages.
- `extract/`: Python scripts used for OCR processing, text parsing, and data extraction from source materials.
- `quartz/`: The underlying Quartz engine and UI components.

## Development

This project requires [Node.js](https://nodejs.org/) (v18 or higher).

### Getting Started

1.  **Install dependencies:**
    ```bash
    npm install
    ```
2.  **Run the development server:**
    ```bash
    npx quartz build --serve
    ```
3.  **Build for production:**
    ```bash
    npx quartz build
    ```

## Data Extraction

The cases are extracted from provided source texts using the scripts in the `extract/` directory.

- `extract_cases.py` / `wonders_parser.py`: Parses raw text and creates structured JSON.
- `json_to_markdown.py`: Generates the Quartz-compatible Markdown files in `content/cases/`.

## License

The code for this project is licensed under the [MIT License](LICENSE.txt). The content is based on the research and works of Jacques Vallée.

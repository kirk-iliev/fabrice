# Fabrice — Vallée's UFO Catalog

A searchable wiki of UFO close encounter cases drawn from Jacques Vallée's *Passport to Magonia* (1969). This project uses [Quartz](https://quartz.jzhao.xyz/) as its publishing engine to organize 923 cases spanning 1897 to 1968.

🔗 **Live Site:** [https://kirk-iliev.github.io/fabrice](https://kirk-iliev.github.io/fabrice)

## About

*Passport to Magonia* catalogs 923 UFO close encounter reports collected by Jacques Vallée, organized chronologically. This project digitizes the appendix, making it searchable and cross-referenced by location, date, and phenomenon type.

### Features

- **Searchable Index:** Quick access to all 923 cases.
- **Categorization:** Cases are tagged by classification (CE1, CE2, CE3), phenomena (humanoid, trace-evidence), and more.
- **Geographic & Chronological Linking:** Quartz backlinks and tags connect cases sharing locations or timeframes.

## Project Structure

- `content/`: The Markdown files for each case and site pages.
- `extract/`: Python scripts used for OCR processing and data extraction from the source PDF.
- `quartz/`: The underlying Quartz engine and UI components.
- `JacquesValleePassporttoMagonia.pdf`: The original source material.

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

The cases are extracted from the provided PDF using the scripts in the `extract/` directory.

- `extract_cases.py`: Parses the text and creates initial JSON.
- `fix_cases.py`: Cleans up OCR errors and formats data.
- `json_to_markdown.py`: Generates the Quartz-compatible Markdown files in `content/cases/`.

## License

The code for this project is licensed under the [MIT License](LICENSE.txt). The content is based on the work of Jacques Vallée.

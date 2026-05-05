# AI-Assisted Visualization Builder for Business Data

## Capstone Title

AI-Assisted Visualization Builder for Business Data

## Project Description / Scope

Build a web-based AI-assisted visualization builder that allows users to upload structured datasets, describe what they want in plain English, and automatically generate visualizations, chart recommendations, summary insights, and downloadable outputs. The system will use a Python-first stack for data ingestion, profiling, transformation, and chart generation, while Claude Code can support the development workflow for code generation, refactoring, prompt iteration, and rapid feature implementation.

The application will accept user instructions such as:
- “Show monthly payroll trend by department”
- “Compare employee count across regions”
- “Find anomalies in overtime hours”

The platform will translate those requests into chart logic and rendering steps.

### Core scope
- Dataset upload
- Schema detection
- Metadata extraction
- Prompt-to-chart generation
- Chart customization
- Data validation
- User feedback loop
- Export functionality

### Optional advanced scope
- Auto-generated narratives
- Anomaly highlighting
- Recommended follow-up charts
- Reusable chart templates for repeated business reporting use cases

### Key capabilities in scope
- Upload CSV, Excel, and JSON files
- Parse schema and profile columns automatically
- Let users ask for charts in natural language
- Recommend best-fit visualizations based on data type and intent
- Generate charts using Python libraries
- Render visual outputs in the website
- Provide chart summaries and basic insights
- Allow users to refine results interactively
- Export visualizations as PNG, PDF, or shareable dashboard views

## Conceptual Data Model

### Main entities

#### 1. User
- `user_id`
- `name`
- `email`
- `role`

#### 2. Dataset
- `dataset_id`
- `user_id`
- `file_name`
- `source_type`
- `upload_timestamp`
- `row_count`
- `column_count`
- `schema_version`

#### 3. Data Column Metadata
- `column_id`
- `dataset_id`
- `column_name`
- `detected_data_type`
- `null_percentage`
- `unique_count`
- `min_value`
- `max_value`
- `sample_values`

#### 4. Prompt Request
- `request_id`
- `user_id`
- `dataset_id`
- `prompt_text`
- `request_timestamp`
- `interpreted_intent`
- `status`

#### 5. Visualization Spec
- `viz_id`
- `request_id`
- `chart_type`
- `x_axis`
- `y_axis`
- `aggregation`
- `filters`
- `grouping`
- `title`
- `color_encoding`

#### 6. Generated Output
- `output_id`
- `viz_id`
- `output_path`
- `output_format`
- `generated_timestamp`
- `insight_summary`

#### 7. Feedback
- `feedback_id`
- `output_id`
- `user_id`
- `rating`
- `comments`
- `revision_requested`

## Conceptual Diagram

```text
+------------------+
|       User       |
+------------------+
| user_id          |
| name             |
| email            |
| role             |
+---------+--------+
          |
          | uploads / requests
          v
+------------------+
|     Dataset      |
+------------------+
| dataset_id       |
| user_id          |
| file_name        |
| source_type      |
| upload_timestamp |
| row_count        |
| column_count     |
| schema_version   |
+---------+--------+
          |
          | has
          v
+------------------------+
|  Data Column Metadata  |
+------------------------+
| column_id              |
| dataset_id             |
| column_name            |
| detected_data_type     |
| null_percentage        |
| unique_count           |
| min_value / max_value  |
| sample_values          |
+------------------------+

          +---------------------------------------------+
          |                                             |
          | user asks in natural language               |
          v                                             |
+------------------+                                    |
|  Prompt Request  |                                    |
+------------------+                                    |
| request_id       |                                    |
| user_id          |                                    |
| dataset_id       |                                    |
| prompt_text      |                                    |
| interpreted_intent                                   |
| status           |                                    |
+---------+--------+                                    |
          |                                             |
          | converted into                              |
          v                                             |
+------------------+                                    |
| Visualization    |                                    |
| Spec             |                                    |
+------------------+                                    |
| viz_id           |                                    |
| request_id       |                                    |
| chart_type       |                                    |
| x_axis           |                                    |
| y_axis           |                                    |
| aggregation      |                                    |
| filters          |                                    |
| grouping         |                                    |
| title            |                                    |
+---------+--------+                                    |
          |                                             |
          | generates                                   |
          v                                             |
+------------------+                                    |
| Generated Output |                                    |
+------------------+                                    |
| output_id        |                                    |
| viz_id           |                                    |
| output_path      |                                    |
| output_format    |                                    |
| insight_summary  |                                    |
| generated_time   |                                    |
+---------+--------+                                    |
          |                                             |
          | receives feedback                           |
          v                                             |
+------------------+                                    |
|     Feedback     |------------------------------------+
+------------------+
| feedback_id      |
| output_id        |
| user_id          |
| rating           |
| comments         |
| revision_request |
+------------------+
```

## System Flow Diagram

```text
[User Uploads File]
        |
        v
[File Intake Layer]
        |
        v
[Data Parsing and Validation]
        |
        v
[Schema Detection + Profiling Engine]
        |
        v
[Metadata Store]
        |
        +-------------------------------+
        |                               |
        v                               v
[Natural Language Prompt]        [Dataset Context]
        |                               |
        +---------------+---------------+
                        |
                        v
             [Prompt Interpretation Layer]
                        |
                        v
            [Visualization Recommendation]
                        |
                        v
         [Python Chart Generation Engine]
          (Matplotlib / Plotly / Seaborn)
                        |
                        v
               [Rendered Visualization]
                        |
                        v
         [Insight Summary + User Feedback Loop]
                        |
                        v
              [Export / Save / Re-generate]
```

## Tools, Data Sources, and Formats

### Frontend
- Streamlit for faster Python-first web app development, or Flask/FastAPI with a lightweight frontend
- HTML, CSS, JavaScript for UI enhancements
- Optional React frontend if a richer interactive experience is needed

### Backend
- Python
- FastAPI or Flask for APIs
- Pandas for data processing
- NumPy for numerical handling
- Pydantic for request validation

### Visualization Layer
- Matplotlib for chart rendering
- Plotly as an optional enhancement for interactive charts
- D3.js only if a custom front-end visualization layer is later required

### AI / LLM Layer
- Claude API for natural language interpretation, chart recommendation, prompt understanding, and insight generation
- Claude Code for development acceleration, code scaffolding, debugging assistance, and rapid iteration

### Data Handling / Storage
- Local file storage or object storage for uploaded files
- SQLite or PostgreSQL for metadata, prompt history, chart specs, and feedback
- Redis optional for caching repeated prompts or dataset summaries

### Data Sources
- User-uploaded business datasets
- Sample public datasets for demos such as payroll, sales, healthcare operations, finance, HR, and supply chain

### Supported Formats
- CSV
- XLSX
- JSON
- Parquet as an advanced extension

## Ingestion Strategy

The ingestion pipeline begins when a user uploads a file through the website. The backend validates file type, size, encoding, and structural integrity before loading it into a Pandas DataFrame. Once loaded, a profiling layer scans the dataset to detect schema, infer data types, estimate missing values, identify duplicates, and generate descriptive metadata. This metadata is stored separately so the prompt interpretation layer can understand the structure of the uploaded data before suggesting charts. If the user enters a prompt, the system combines prompt text with dataset metadata and sends both to the LLM to determine user intent, appropriate chart type, required columns, and aggregation logic. The backend then applies the transformation logic, prepares a clean filtered dataset, and passes it into the chart generation engine. The rendered chart and summary are returned to the UI, where the user can approve, refine, or request another version.

### Suggested ingestion stages
1. File upload and format validation
2. Schema extraction and column profiling
3. Data type standardization
4. Null and duplicate assessment
5. Metadata generation and storage
6. Prompt + metadata interpretation
7. Transformation and aggregation
8. Chart rendering and feedback capture

## Data Quality Checks

To make the platform reliable, the system should apply data quality rules before building charts. These checks prevent misleading visualizations and reduce chart generation failures.

### Recommended checks
- File validation: reject unsupported or corrupted files
- Schema validation: confirm consistent headers and readable structure
- Null checks: calculate missing value percentages per column
- Duplicate checks: identify duplicate records or repeated headers
- Data type validation: ensure numeric, categorical, and date fields are correctly inferred
- Range validation: detect negative values in fields that should not be negative, such as salary or sales quantity
- Date validation: confirm valid date formats and convert them into a standard format
- Outlier detection: flag extreme values that may distort visualization
- Aggregation readiness: verify that selected columns support the requested chart logic
- Prompt-to-data alignment: confirm the fields requested by the user actually exist in the dataset
- Visualization compatibility check: prevent unsupported combinations such as pie chart on high-cardinality dimensions or line chart without ordered data

### Example validation outcomes
- “Department column has 12% missing values”
- “Date column contains mixed formats”
- “Requested metric ‘revenue’ not found; closest match is ‘total_revenue’”
- “Scatter plot recommended instead of bar chart due to continuous variables”

## Success Metrics

### Technical metrics
- Prompt-to-chart success rate
- Chart generation response time
- Data parsing accuracy
- Schema detection accuracy
- Failure rate for invalid prompt-to-column mapping
- Percentage of prompts resolved without manual correction

### User experience metrics
- User satisfaction rating per generated output
- Number of chart refinements per request
- Time taken from upload to first usable chart
- Percentage of accepted first-attempt visualizations
- Repeat usage rate

### Business and product metrics
- Reduction in manual chart-building effort
- Faster insight generation for business users
- Improved accessibility for non-technical users
- Higher report generation efficiency

### Sample target metrics
- 85%+ first-pass chart generation success
- Under 10 seconds average response for medium-sized datasets
- 70%+ user acceptance within first two iterations
- 50% reduction in time spent building basic business charts manually

## Stakeholder Value

### Business users
- Can create charts without needing SQL, Python, or BI tool expertise
- Get faster answers from raw uploaded data
- Reduce dependency on analysts for simple reporting needs

### Data analysts
- Save time on repetitive visualization requests
- Can focus on deeper analysis instead of routine chart generation
- Gain a reusable assistant for exploratory data analysis

### Managers and decision-makers
- Get quicker access to understandable visuals and trend summaries
- Improve reporting speed during operations, payroll review, finance analysis, and performance tracking

### Engineering teams
- Build a reusable AI-powered analytics product pattern
- Demonstrate practical integration of LLMs with structured data systems
- Create a foundation for future features such as dashboards, auto-insights, anomaly detection, and conversational analytics

### Example stakeholder use cases
- HR manager uploads payroll data and asks for overtime trend by department
- Operations lead uploads staffing data and requests attrition distribution by region
- Finance analyst uploads expense data and asks for monthly variance chart with anomaly highlighting

## Proposed Architecture

```text
+------------------------------------------------------+
|                    Web Application                   |
|     Upload UI | Prompt Box | Chart View | Export     |
+-----------------------------+------------------------+
                              |
                              v
+------------------------------------------------------+
|                    API Layer                         |
|         FastAPI / Flask request handling             |
+-----------------------------+------------------------+
                              |
             +----------------+----------------+
             |                                 |
             v                                 v
+---------------------------+       +---------------------------+
|    File Ingestion Layer   |       |   Prompt Interpretation  |
| CSV/XLSX/JSON parser      |       | Claude API               |
| Pandas loading            |       | intent extraction        |
| validation rules          |       | chart recommendation     |
+-------------+-------------+       +-------------+-------------+
              |                                       |
              v                                       |
+---------------------------+                         |
| Schema Profiling Engine   |-------------------------+
| datatype inference        |
| null checks               |
| duplicates                |
| statistics                |
+-------------+-------------+
              |
              v
+---------------------------+
| Metadata / App Database   |
| dataset metadata          |
| prompt history            |
| visualization specs       |
| feedback                  |
+-------------+-------------+
              |
              v
+---------------------------+
| Chart Generation Engine   |
| Pandas transformations    |
| Matplotlib / Plotly       |
+-------------+-------------+
              |
              v
+---------------------------+
| Output Renderer           |
| image/chart display       |
| summary generation        |
| export PNG/PDF            |
+---------------------------+
```

## Deliverables

- Working web application
- Upload and data profiling module
- Natural language to chart generation workflow
- Visualization rendering engine
- Data validation layer
- Metadata tracking database
- Feedback loop for chart refinement
- Final presentation with architecture, demo, and evaluation metrics

## Future Enhancements

- Dashboard generation from multiple prompts
- Auto-insight narration for each chart
- Role-based access for team collaboration
- Template memory for repeated reporting patterns
- Anomaly detection and forecasting
- Support for database connectors instead of only file uploads
- Chat-based analytics assistant over uploaded data

## One-line project summary

A Python-first AI visualization builder that transforms uploaded structured data and natural language prompts into validated charts, insights, and reusable analytics outputs through an intelligent web application.

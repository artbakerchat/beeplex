from pathlib import Path
from datetime import date, datetime

import pandas as pd
from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
from pptx import Presentation
from pptx.util import Inches, Pt as PptxPt
from openpyxl import load_workbook
from openpyxl.styles import Font, Alignment
from bee_fetcher import fetch_report_data

OUTPUT_DIR = Path(__file__).resolve().parent / "family"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
# 1. Conversation data - live from the Bee CLI (falls back to clearly-labelled
# mock data when the CLI is missing or not authenticated).
bee_transcript_data, bee_source = fetch_report_data(limit=10)
print(f"Bee data source: {bee_source['mode']} - {bee_source['detail']}")

# Report date = most recent Bee recording date (the actual date Bee captured
# the conversations), falling back to today.
_recording_dates = [r["Recording_Date"] for r in bee_transcript_data if r.get("Recording_Date")]
GENERATED_DATE = max(_recording_dates) if _recording_dates else date.today()
DISPLAY_DATE = GENERATED_DATE.strftime("%B %d, %Y").replace(" 0", " ")
GENERATED_AT = datetime.now()
DOCUMENT_TITLE = f"Bee Wearable - Conversation & Transcript Log \u2014 {DISPLAY_DATE}"
EXCEL_TITLE = f"Bee Transcript Metrics \u2014 {DISPLAY_DATE}"
PRESENTATION_TITLE = f"Bee Wearable AI Insights \u2014 {DISPLAY_DATE}"

# 2. Generate Word Document
doc = Document()
doc.core_properties.title = DOCUMENT_TITLE
doc.core_properties.created = GENERATED_AT
doc.core_properties.modified = GENERATED_AT
doc.add_heading(DOCUMENT_TITLE, 0)
doc.add_paragraph(f"Generated: {DISPLAY_DATE}")
doc.add_paragraph("Processed from text transcripts (Raw audio is automatically deleted post-transcription by Bee).")

for item in bee_transcript_data:
    p = doc.add_paragraph(style='List Bullet')
    run = p.add_run(f"Session: {item['Session_Title']} — Topic: {item['Key_Topic']} ")
    run.bold = True
    p.add_run(f"(Tone: {item['Tone_Rating']} | Engagement: {item['Engagement_Level']} | Forward Motion: {item['Forward_Motion']})\n")
    run = p.add_run(f"Transcript Excerpt: \"{item['Source_Transcript_Snippet']}\"\n")
    run.italic = True
    p.add_run(f"Action Items: {item['Action_Items']}\n")
    p.add_run(f"Summary: {item['Summary_Notes']}")

filename = f"Bee_Transcript_Action_Log_{GENERATED_DATE}.docx"
doc.save(OUTPUT_DIR / filename)
print(f"Saved: {filename}")

# 3. Generate Excel Spreadsheet
df = pd.DataFrame(bee_transcript_data)
filename = f"Bee_Transcript_Metrics_{GENERATED_DATE}.xlsx"
excel_path = OUTPUT_DIR / filename
df.to_excel(excel_path, index=False, sheet_name='Sheet1')

# Format workbook
workbook = load_workbook(excel_path)
workbook.properties.title = EXCEL_TITLE
workbook.properties.created = GENERATED_AT
workbook.properties.modified = GENERATED_AT

# Auto-adjust column widths
worksheet = workbook.active
column_widths = [16, 25, 74, 26, 24, 23, 20, 21, 26]
for i, width in enumerate(column_widths, 1):
    worksheet.column_dimensions[chr(64 + i)].width = width

# Bold header row
for cell in worksheet[1]:
    cell.font = Font(bold=True)
    cell.alignment = Alignment(horizontal='center')

workbook.save(excel_path)
print(f"Saved: {filename}")

# 4. Generate PowerPoint Presentation
prs = Presentation()
prs.core_properties.title = PRESENTATION_TITLE
prs.core_properties.created = GENERATED_AT
prs.core_properties.modified = GENERATED_AT

# Slide 1: Title slide
slide1 = prs.slides.add_slide(prs.slide_layouts[0])
slide1.shapes.title.text = PRESENTATION_TITLE
slide1.placeholders[1].text = f"Transcript Summaries & Action Items Review — {DISPLAY_DATE}"

# Slide 2: Key Modules / Key Takeaways
slide2 = prs.slides.add_slide(prs.slide_layouts[1])
slide2.shapes.title.text = "Key Modules"
tf = slide2.placeholders[1].text_frame
tf.text = ""

first_item = bee_transcript_data[0]
p = tf.add_paragraph()
p.text = first_item['Session_Title']
p.level = 0

p = tf.add_paragraph()
p.text = f"Action Item: {first_item['Action_Items'].split(';')[0].strip()}"
p.level = 1

action_items = first_item['Action_Items'].split(';')
for action in action_items[1:]:
    p = tf.add_paragraph()
    p.text = action.strip()
    p.level = 1

p = tf.add_paragraph()
p.text = ""
p.level = 1

for i in range(1, 6):
    p = tf.add_paragraph()
    p.text = f"Module {i}:"
    p.level = 1

# Slides 3 & 4: Individual session slides
for idx, item in enumerate(bee_transcript_data[1:], 3):
    slide = prs.slides.add_slide(prs.slide_layouts[1])
    slide.shapes.title.text = str(idx - 1)

    tf = slide.placeholders[1].text_frame
    tf.text = f"{item['Session_Title']} [{item['Tone_Rating']}]"

    p = tf.add_paragraph()
    p.text = f"Action: {item['Action_Items']}"
    p.level = 0

filename = f"Bee_Insights_Presentation_{GENERATED_DATE}.pptx"
prs.save(OUTPUT_DIR / filename)
print(f"Saved: {filename}")

print("Successfully generated updated Bee Wearable Word, Excel, and PowerPoint files!")

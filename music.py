import pandas as pd
from docx import Document
from pptx import Presentation

# Simulated text transcript data pulled from a session log
transcript_notes = [
    {"Timestamp": "00:15:20", "Category": "Lyrics", "Feedback": "Decided to change the second verse to focus on family conflict themes."},
    {"Timestamp": "00:28:45", "Category": "Vocal Delivery", "Feedback": "Tone needs to feel more vulnerable and conversational on the bridge."},
    {"Timestamp": "00:42:10", "Category": "Arrangement", "Feedback": "Agreed to strip back the acoustic guitar layer to let the vocals breathe."}
]

# 1. Word Document: Comprehensive Session Log
doc = Document()
doc.add_heading("Music Session Transcript Insights", 0)
doc.add_paragraph("Extracted notes and decisions from spoken studio dialogue.")

for note in transcript_notes:
    p = doc.add_paragraph(style='List Bullet')
    p.add_run(f"[{note['Timestamp']}] {note['Category']}: ").bold = True
    p.add_run(note['Feedback'])

doc.save("Session_Transcript_Summary.docx")

# 2. Excel Spreadsheet: Categorized Action Tracking
df = pd.DataFrame(transcript_notes)
df.to_excel("Session_Action_Matrix.xlsx", index=False)

# 3. PowerPoint: Creative Direction Deck
prs = Presentation()
slide = prs.slides.add_slide(prs.slide_layouts[0])
slide.shapes.title.text = "Studio Creative Review"
slide.placeholders[1].text = "Key Decisions from Spoken Transcripts"

bullet_slide = prs.slides.add_slide(prs.slide_layouts[1])
bullet_slide.shapes.title.text = "Action Items & Flow Adjustments"
tf = bullet_slide.placeholders[1].text_frame
tf.text = "Highlights from Session Dialogue:"

for note in transcript_notes:
    p = tf.add_paragraph()
    p.text = f"{note['Category']}: {note['Feedback']}"

prs.save("Session_Creative_Direction.pptx")

print("Generated Office suite documents successfully using text transcripts!")

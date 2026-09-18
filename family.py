import pandas as pd
from docx import Document
from pptx import Presentation

# 1. Simulate data parsed from Bee Wearable text transcripts 
# (Note: Bee records ambient audio, transcribes it in real-time, deletes raw audio, 
# and exports text transcripts with summaries, action items, and insights)
bee_transcript_data = [
    {
        "Session_Title": "Product Strategy Sync",
        "Source_Transcript_Snippet": "...we need to finalize the Q3 roadmap by Friday and assign module owners...",
        "Key_Topic": "Roadmap Deadlines",
        "Tone_Rating": 7,
        "Engagement_Level": "High",
        "Action_Items": "Finalize Q3 roadmap by Friday; assign module owners.",
        "Summary_Notes": "Team aligned on core priorities and established strict delivery milestones."
    },
    {
        "Session_Title": "Client Feedback Review",
        "Source_Transcript_Snippet": "...the client mentioned latency issues during peak hours, need an urgent patch...",
        "Key_Topic": "Performance Bug",
        "Tone_Rating": 4,
        "Engagement_Level": "Moderate",
        "Action_Items": "Deploy latency patch before Monday peak hours.",
        "Summary_Notes": "Addressed urgent customer friction point; engineering team to investigate."
    },
    {
        "Session_Title": "Weekly Team Catch-up",
        "Source_Transcript_Snippet": "...everyone's workload looks balanced, let's keep the current sprint velocity...",
        "Key_Topic": "Workload & Velocity",
        "Tone_Rating": 9,
        "Engagement_Level": "High",
        "Action_Items": "Maintain current sprint tasks; schedule next retro.",
        "Summary_Notes": "Positive alignment; team morale is high and pacing is sustainable."
    }
]

# 2. Generate Word Document (Bee Transcript & Action Log)
doc = Document()
doc.add_heading("Bee Wearable - Conversation & Transcript Log", 0)
doc.add_paragraph("Processed from text transcripts (Raw audio is automatically deleted post-transcription by Bee).")

for item in bee_transcript_data:
    p = doc.add_paragraph(style='List Bullet')
    p.add_run(f"Session: {item['Session_Title']} — Topic: {item['Key_Topic']} ").bold = True
    p.add_run(f"(Tone: {item['Tone_Rating']}/10 | Engagement: {item['Engagement_Level']})\n")
    p.add_run(f"Transcript Excerpt: \"{item['Source_Transcript_Snippet']}\"\n").italic = True
    p.add_run(f"Action Items: {item['Action_Items']}\n")
    p.add_run(f"Summary: {item['Summary_Notes']}")

doc.save("Bee_Transcript_Action_Log.docx")

# 3. Generate Excel Spreadsheet (Transcript Metrics & Action Tracker)
df = pd.DataFrame(bee_transcript_data)
df.to_excel("Bee_Transcript_Metrics.xlsx", index=False)

# 4. Generate PowerPoint Presentation (Bee Insights Deck)
prs = Presentation()
slide = prs.slides.add_slide(prs.slide_layouts[0])
slide.shapes.title.text = "Bee Wearable AI Insights"
slide.placeholders[1].text = "Transcript Summaries & Action Items Review"

# Add summary bullet points
bullet_slide = prs.slides.add_slide(prs.slide_layouts[1])
bullet_slide.shapes.title.text = "Key Takeaways from Transcripts"
tf = bullet_slide.placeholders[1].text_frame
tf.text = "Summary of Bee Device Transcripts:"

for item in bee_transcript_data:
    p = tf.add_paragraph()
    p.text = f"{item['Session_Title']} ({item['Key_Topic']}) -> Action: {item['Action_Items']}"

prs.save("Bee_Insights_Presentation.pptx")

print("Successfully generated Bee Wearable Word, Excel, and PowerPoint files from text transcripts!")
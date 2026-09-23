import React, { useEffect, useState } from "react"
import {
  Streamlit,
  withStreamlitConnection,
  ComponentProps,
} from "streamlit-component-lib"

interface Conversation {
  date: string
  title: string
  topic: string
}

const cardStyle = (active: boolean): React.CSSProperties => ({
  border: active ? "2px solid #E8A317" : "1px solid #E8DCC0",
  borderRadius: "12px",
  padding: "12px 16px",
  cursor: "pointer",
  background: active ? "#FFF6DE" : "#FFFDF5",
  minWidth: "220px",
  maxWidth: "280px",
  transition: "box-shadow 0.15s ease",
  boxShadow: active ? "0 4px 12px rgba(200,130,10,0.25)" : "none",
})

function ConversationCards({ args }: ComponentProps) {
  const conversations: Conversation[] = args["conversations"] || []
  const [selected, setSelected] = useState<number | null>(null)

  useEffect(() => {
    Streamlit.setFrameHeight()
  })

  const pick = (i: number) => {
    setSelected(i)
    // Two-way: send the clicked conversation back to Python.
    Streamlit.setComponentValue(conversations[i])
  }

  if (conversations.length === 0) {
    return (
      <div style={{ color: "#8A6D3B", fontStyle: "italic" }}>
        No conversations to show.
      </div>
    )
  }

  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: "12px" }}>
      {conversations.map((c, i) => (
        <div key={i} onClick={() => pick(i)} style={cardStyle(selected === i)}>
          <div style={{ fontWeight: 700, color: "#3A2E1A" }}>
            {c.title || "(untitled)"}
          </div>
          <div style={{ fontSize: "13px", color: "#8A6D3B" }}>{c.date}</div>
          <div style={{ fontSize: "13px", color: "#5A4A2A", marginTop: "4px" }}>
            {c.topic}
          </div>
        </div>
      ))}
    </div>
  )
}

export default withStreamlitConnection(ConversationCards)

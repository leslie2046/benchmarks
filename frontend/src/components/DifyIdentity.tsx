import { BookOpen, MessageSquare } from "lucide-react";
import { tr, type Language } from "../i18n";

export function DifyTypeIcon({ benchmark, language }: { benchmark: string; language: Language }) {
  const chat = benchmark === "dify-chat";
  const label = tr(language, chat ? "聊天应用" : "知识库检索");
  return <span className={`dify-type-icon ${chat ? "dify-type-chat" : "dify-type-knowledge"}`} role="img" aria-label={label} title={label}>
    {chat ? <MessageSquare aria-hidden="true" /> : <BookOpen aria-hidden="true" />}
  </span>;
}

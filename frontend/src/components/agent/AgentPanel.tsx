import { AgentConversation } from "./Conversation"
import { ConversationHistory } from "./ConversationHistory"
import type { AgentChat } from "./useAgentChat"

/** Body of the agent panel: the conversation, or the saved ones. Loaded when first opened. */
export function AgentPanel({ chat, onNavigate }: { chat: AgentChat; onNavigate: () => void }) {
  if (chat.showHistory)
    return (
      <ConversationHistory
        current={chat.conversationId}
        onOpen={(id) => void chat.resume(id)}
        onDeleted={(id) => {
          if (id === chat.conversationId) chat.begin(null, null)
        }}
      />
    )
  return (
    <AgentConversation
      turns={chat.turns}
      pending={chat.pending}
      onAsk={chat.ask}
      onStop={chat.stop}
      onNavigate={onNavigate}
      viewing={chat.about}
      onIgnoreViewing={chat.ignoreViewing}
      previous={chat.previous}
      onResume={(id) => void chat.resume(id)}
    />
  )
}

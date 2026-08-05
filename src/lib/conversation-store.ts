/**
 * Per-conversation turn storage for the chat model.
 *
 * Why this exists: prompt caching only pays out when a request shares a
 * byte-identical *prefix* with a recent one. A chat request is `[systemInstruction, ...history,
 * newTurn]`, so turn N is only cacheable if `history` reproduces exactly what was sent on turn
 * N-1 — including the retrieved source context. Storing only the user's question (or a
 * re-formatted history string) changes the prefix on every turn and yields zero cache hits.
 *
 * Turns are therefore stored verbatim, keyed by conversation. Entries are in-memory and
 * best-effort: a restart or a second server instance just means the next turn starts cold, which
 * degrades to the previous behaviour rather than breaking the chat.
 */

export interface ConversationTurn {
  role: 'user' | 'model';
  parts: { text: string }[];
}

/** Turns kept per conversation (user + model counted separately). Older ones are dropped. */
export const MAX_TURNS_PER_CONVERSATION = 8;
/** Conversations kept in memory before the least recently used ones are evicted. */
export const MAX_CONVERSATIONS = 500;
/** How long an idle conversation survives. The provider's prompt cache is far shorter lived. */
export const CONVERSATION_TTL_MS = 30 * 60 * 1000;

interface ConversationEntry {
  turns: ConversationTurn[];
  updatedAt: number;
}

const conversations = new Map<string, ConversationEntry>();

const isExpired = (entry: ConversationEntry, now: number): boolean =>
  now - entry.updatedAt > CONVERSATION_TTL_MS;

const pruneExpired = (now: number): void => {
  for (const [id, entry] of conversations) {
    if (isExpired(entry, now)) {
      conversations.delete(id);
    }
  }
};

const evictOverflow = (): void => {
  // Map preserves insertion order and every write re-inserts, so the head is the oldest entry.
  while (conversations.size > MAX_CONVERSATIONS) {
    const oldest = conversations.keys().next();
    if (oldest.done) {
      return;
    }
    conversations.delete(oldest.value);
  }
};

/**
 * Returns the stored turns for a conversation, or an empty history when there is nothing usable.
 * The returned array is a copy: callers may hand it straight to the model request builder.
 */
export const getConversationTurns = (conversationId?: string): ConversationTurn[] => {
  if (!conversationId) {
    return [];
  }

  const now = Date.now();
  pruneExpired(now);

  const entry = conversations.get(conversationId);
  if (!entry) {
    return [];
  }

  return entry.turns.map((turn) => ({ role: turn.role, parts: turn.parts.map((part) => ({ ...part })) }));
};

/**
 * Appends one completed exchange, storing the prompt exactly as it was sent so the next request
 * extends this one instead of diverging from it.
 */
export const appendConversationTurn = (
  conversationId: string | undefined,
  userPrompt: string,
  modelAnswer: string
): void => {
  if (!conversationId || !userPrompt || !modelAnswer) {
    return;
  }

  const now = Date.now();
  pruneExpired(now);

  const existing = conversations.get(conversationId);
  const turns = existing && !isExpired(existing, now) ? existing.turns : [];

  turns.push({ role: 'user', parts: [{ text: userPrompt }] });
  turns.push({ role: 'model', parts: [{ text: modelAnswer }] });

  // Trim in whole exchanges so history never starts on an assistant turn.
  if (turns.length > MAX_TURNS_PER_CONVERSATION) {
    turns.splice(0, turns.length - MAX_TURNS_PER_CONVERSATION);
  }

  // Delete first so the re-insert moves this conversation to the tail for LRU eviction.
  conversations.delete(conversationId);
  conversations.set(conversationId, { turns, updatedAt: now });
  evictOverflow();
};

export const clearConversation = (conversationId: string): void => {
  conversations.delete(conversationId);
};

export const clearAllConversations = (): void => {
  conversations.clear();
};

export const getConversationCount = (): number => conversations.size;

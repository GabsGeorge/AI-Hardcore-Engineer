import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/** Renderiza Markdown vindo do agente de forma segura: react-markdown nao avalia HTML cru
 * nem URLs javascript:, entao o modelo nao consegue injetar script (FR-012 na UI; o backend
 * ja esta coberto em tests/security/test_chat_render.py). GFM habilita tabelas, listas
 * de tarefas e strikethrough que o LLM gera naturalmente. */
export function MessageContent({ text }: { text: string }) {
  return (
    <div className="prose prose-sm [&_code]:rounded [&_code]:py-0.5 max-w-none text-ink-700 [&_a]:text-support [&_a]:underline [&_code]:bg-surface-200 [&_code]:px-1 [&_ol]:ml-4 [&_ol]:list-decimal [&_pre]:overflow-auto [&_pre]:rounded-md [&_pre]:bg-surface-200 [&_pre]:p-2 [&_table]:border-collapse [&_td]:border [&_td]:border-line [&_td]:px-2 [&_td]:py-1 [&_th]:border [&_th]:border-line [&_th]:px-2 [&_th]:py-1 [&_ul]:ml-4 [&_ul]:list-disc">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ node: _node, children, ...props }) => (
            <a {...props} target="_blank" rel="noopener noreferrer">
              {children}
            </a>
          ),
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}

const state = { conversationId: null };
const chat = document.querySelector('#chat');
const messages = document.querySelector('#messages');
const welcome = document.querySelector('#welcome');
const composer = document.querySelector('#composer');
const messageInput = document.querySelector('#message');
const sendButton = document.querySelector('#send');
const dialog = document.querySelector('#knowledge-dialog');
const isAdmin = window.location.pathname === '/admin';
const adminKey = isAdmin ? window.prompt('Enter the admin key') : null;

function addMessage(role, content, sources = []) {
  welcome.hidden = true;
  const row = document.createElement('article');
  row.className = `message ${role}`;
  const uniqueSources = sources.filter((source, index, allSources) => allSources.findIndex((item) => item.title === source.title) === index);
  const sourceHtml = uniqueSources.length ? uniqueSources.map((source) => {
    const imageUrls = [...new Set(source.image_urls || (source.image_url ? [source.image_url] : []))];
    const imageHtml = imageUrls.length ? `<div class="source-gallery">${imageUrls.map((imageUrl) => `<img src="${imageUrl}" alt="${escapeHtml(source.title)}" class="source-image" loading="lazy" />`).join('')}</div>` : '';
    return `<div class="source-item"><small class="sources">${escapeHtml(source.title)}</small>${imageHtml}</div>`;
  }).join('') : '';
  const contentHtml = role === 'assistant' ? formatAssistantContent(content) : `<p>${escapeHtml(content).replaceAll('\n', '<br>')}</p>`;
  row.innerHTML = `<div class="avatar">${role === 'assistant' ? 'L' : 'You'}</div><div class="bubble"><small>${role === 'assistant' ? 'LUMEN' : 'YOU'}</small>${contentHtml}${sourceHtml}</div>`;
  messages.append(row);
  chat.scrollTop = chat.scrollHeight;
}

function escapeHtml(value) { return value.replace(/[&<>'"]/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[character]); }

function formatAssistantContent(value) {
  const lines = escapeHtml(value).split('\n');
  const output = [];
  let listType = null;

  const closeList = () => {
    if (listType) {
      output.push(`</${listType}>`);
      listType = null;
    }
  };

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) {
      closeList();
      continue;
    }

    const heading = trimmed.match(/^#{1,3}\s+(.+)$/);
    const bullet = trimmed.match(/^[-*]\s+(.+)$/);
    const numbered = trimmed.match(/^\d+[.)]\s+(.+)$/);

    if (heading) {
      closeList();
      output.push(`<h3>${formatInlineMarkdown(heading[1])}</h3>`);
    } else if (bullet || numbered) {
      const nextListType = bullet ? 'ul' : 'ol';
      if (listType !== nextListType) {
        closeList();
        listType = nextListType;
        output.push(`<${listType}>`);
      }
      output.push(`<li>${formatInlineMarkdown((bullet || numbered)[1])}</li>`);
    } else {
      closeList();
      output.push(`<p>${formatInlineMarkdown(trimmed)}</p>`);
    }
  }

  closeList();
  return output.join('');
}

function formatInlineMarkdown(value) {
  return value.replace(/(\*\*|__)(.+?)\1/g, '<strong>$2</strong>');
}

async function sendMessage(content) {
  if (!content.trim() || sendButton.disabled) return;
  addMessage('user', content);
  messageInput.value = '';
  sendButton.disabled = true;
  const thinking = document.createElement('div');
  thinking.className = 'thinking'; thinking.textContent = 'Lumen is retrieving context...'; messages.append(thinking);
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 30000);
    const response = await fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message: content, conversation_id: state.conversationId }), signal: controller.signal });
    clearTimeout(timeout);
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || 'Unable to reach the chat service.');
    state.conversationId = result.conversation_id;
    thinking.remove(); addMessage('assistant', result.answer, result.sources || []);
  } catch (error) { thinking.remove(); addMessage('assistant', error.name === 'AbortError' ? 'The response took too long. Please try again or check that the AI service is available.' : error.message); }
  sendButton.disabled = false; messageInput.focus();
}

composer.addEventListener('submit', (event) => { event.preventDefault(); sendMessage(messageInput.value); });
messageInput.addEventListener('keydown', (event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); composer.requestSubmit(); } });
document.querySelectorAll('[data-prompt]').forEach((button) => button.addEventListener('click', () => { messageInput.value = button.dataset.prompt; messageInput.focus(); }));
document.querySelector('#new-chat').addEventListener('click', () => { state.conversationId = null; messages.replaceChildren(); welcome.hidden = false; });
const shell = document.querySelector('.shell');
const minimizeButton = document.querySelector('#minimize-chat');
const maximizeButton = document.querySelector('#maximize-chat');
minimizeButton.addEventListener('click', () => {
  document.body.classList.toggle('is-minimized');
  const minimized = document.body.classList.contains('is-minimized');
  minimizeButton.setAttribute('aria-label', minimized ? 'Restore chat' : 'Minimize chat');
  minimizeButton.title = minimized ? 'Restore chat' : 'Minimize chat';
});
maximizeButton.addEventListener('click', () => {
  shell.classList.toggle('is-maximized');
  const maximized = shell.classList.contains('is-maximized');
  maximizeButton.textContent = maximized ? '❐' : '□';
  maximizeButton.setAttribute('aria-label', maximized ? 'Restore layout' : 'Maximize chat');
  maximizeButton.title = maximized ? 'Restore layout' : 'Maximize chat';
});
if (isAdmin && adminKey) {
  document.querySelector('#admin-tools').hidden = false;
  document.querySelector('#open-knowledge').addEventListener('click', () => dialog.showModal());
  document.querySelector('.close').addEventListener('click', () => dialog.close());
  document.querySelector('#knowledge-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const status = document.querySelector('#doc-status'); status.textContent = 'Storing and indexing...';
  try {
    const formData = new FormData();
    formData.append('title', document.querySelector('#doc-title').value);
    formData.append('content', document.querySelector('#doc-content').value);
    const file = document.querySelector('#doc-file').files[0];
    if (file) formData.append('file', file);

    const response = await fetch('/api/knowledge', { method: 'POST', headers: { 'X-Admin-Key': adminKey }, body: formData });
    const result = await response.json(); if (!response.ok) throw new Error(result.detail || 'Unable to store document.');
    status.textContent = `Stored ${result.chunks} searchable chunk${result.chunks === 1 ? '' : 's'}.`; await loadDocuments();
    setTimeout(() => { dialog.close(); document.querySelector('#knowledge-form').reset(); status.textContent = ''; }, 600);
  } catch (error) { status.textContent = error.message; }
  });
}

async function loadDocuments() {
  if (!isAdmin || !adminKey) return;
  const response = await fetch('/api/knowledge', { headers: { 'X-Admin-Key': adminKey } }); const result = await response.json();
  document.querySelector('#documents').innerHTML = (result.documents || []).map((document) => `<div class="document"><span>◌</span>${escapeHtml(document.title)}</div>`).join('');
}
if (isAdmin && adminKey) loadDocuments();

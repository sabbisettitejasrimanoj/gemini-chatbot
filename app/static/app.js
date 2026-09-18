const state = { conversationId: null };
const chat = document.querySelector('#chat');
const messages = document.querySelector('#messages');
const welcome = document.querySelector('#welcome');
const composer = document.querySelector('#composer');
const messageInput = document.querySelector('#message');
const sendButton = document.querySelector('#send');
const dialog = document.querySelector('#knowledge-dialog');

function addMessage(role, content, sources = []) {
  welcome.hidden = true;
  const row = document.createElement('article');
  row.className = `message ${role}`;
  const sourceHtml = sources.length ? sources.map((source) => {
    const imageHtml = source.image_url ? `<img src="${source.image_url}" alt="${escapeHtml(source.title)}" class="source-image" />` : '';
    return `<div class="source-item"><small class="sources">${escapeHtml(source.title)}</small>${imageHtml}</div>`;
  }).join('') : '';
  row.innerHTML = `<div class="avatar">${role === 'assistant' ? 'L' : 'You'}</div><div class="bubble"><small>${role === 'assistant' ? 'LUMEN' : 'YOU'}</small><p>${escapeHtml(content).replaceAll('\n', '<br>')}</p>${sourceHtml}</div>`;
  messages.append(row);
  chat.scrollTop = chat.scrollHeight;
}

function escapeHtml(value) { return value.replace(/[&<>'"]/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[character]); }

async function sendMessage(content) {
  if (!content.trim() || sendButton.disabled) return;
  addMessage('user', content);
  messageInput.value = '';
  sendButton.disabled = true;
  const thinking = document.createElement('div');
  thinking.className = 'thinking'; thinking.textContent = 'Lumen is retrieving context...'; messages.append(thinking);
  try {
    const response = await fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message: content, conversation_id: state.conversationId }) });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || 'Unable to reach the chat service.');
    state.conversationId = result.conversation_id;
    thinking.remove(); addMessage('assistant', result.answer, result.sources || []);
  } catch (error) { thinking.remove(); addMessage('assistant', error.message); }
  sendButton.disabled = false; messageInput.focus();
}

composer.addEventListener('submit', (event) => { event.preventDefault(); sendMessage(messageInput.value); });
messageInput.addEventListener('keydown', (event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); composer.requestSubmit(); } });
document.querySelectorAll('[data-prompt]').forEach((button) => button.addEventListener('click', () => { messageInput.value = button.dataset.prompt; messageInput.focus(); }));
document.querySelector('#new-chat').addEventListener('click', () => { state.conversationId = null; messages.replaceChildren(); welcome.hidden = false; });
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

    const response = await fetch('/api/knowledge', { method: 'POST', body: formData });
    const result = await response.json(); if (!response.ok) throw new Error(result.detail || 'Unable to store document.');
    status.textContent = `Stored ${result.chunks} searchable chunk${result.chunks === 1 ? '' : 's'}.`; await loadDocuments();
    setTimeout(() => { dialog.close(); document.querySelector('#knowledge-form').reset(); status.textContent = ''; }, 600);
  } catch (error) { status.textContent = error.message; }
});

async function loadDocuments() {
  const response = await fetch('/api/knowledge'); const result = await response.json();
  document.querySelector('#documents').innerHTML = (result.documents || []).map((document) => `<div class="document"><span>◌</span>${escapeHtml(document.title)}</div>`).join('');
}
loadDocuments();

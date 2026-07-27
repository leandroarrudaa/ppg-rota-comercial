// ============================================================
// Cliente da API do backend (autenticação + chamadas com token).
// Guarda o token no localStorage; 401 derruba a sessão e volta pro login.
// ============================================================

const BASE = import.meta.env.VITE_API_URL || "http://localhost:8090";
const CHAVE_TOKEN = "ppg_token";
const CHAVE_USUARIO = "ppg_usuario";

export function tokenSalvo() {
  return localStorage.getItem(CHAVE_TOKEN);
}

export function usuarioSalvo() {
  try {
    return JSON.parse(localStorage.getItem(CHAVE_USUARIO)) || null;
  } catch {
    return null;
  }
}

export function salvarSessao(token, usuario) {
  localStorage.setItem(CHAVE_TOKEN, token);
  localStorage.setItem(CHAVE_USUARIO, JSON.stringify(usuario));
}

export function limparSessao() {
  localStorage.removeItem(CHAVE_TOKEN);
  localStorage.removeItem(CHAVE_USUARIO);
}

// callback registrado pelo App pra reagir a sessão expirada (volta pro login)
let aoExpirar = null;
export function registrarAoExpirar(fn) {
  aoExpirar = fn;
}

async function chamar(caminho, opcoes = {}) {
  const headers = { "Content-Type": "application/json", ...(opcoes.headers || {}) };
  const token = tokenSalvo();
  if (token) headers.Authorization = `Bearer ${token}`;

  let resp;
  try {
    resp = await fetch(`${BASE}${caminho}`, { ...opcoes, headers });
  } catch {
    throw new Error("Sem conexão com o servidor. Verifique sua internet.");
  }

  // 401 do próprio login/setup é "usuário ou senha incorretos", não sessão
  // expirada (não havia sessão nenhuma) — só trata como expiração quando
  // a chamada ia autenticada com um token que o servidor rejeitou.
  const eraChamadaAutenticada = Boolean(token) && !caminho.startsWith("/api/auth/login") && !caminho.startsWith("/api/auth/setup");
  if (resp.status === 401 && eraChamadaAutenticada) {
    limparSessao();
    if (aoExpirar) aoExpirar();
    throw new Error("Sessão expirada, faça login de novo.");
  }
  if (!resp.ok) {
    let detalhe = "Erro no servidor.";
    try {
      const j = await resp.json();
      if (j.detail) detalhe = typeof j.detail === "string" ? j.detail : "Dados inválidos.";
    } catch { /* resposta sem corpo JSON */ }
    throw new Error(detalhe);
  }
  return resp.json();
}

export const api = {
  get: (caminho) => chamar(caminho),
  post: (caminho, corpo) => chamar(caminho, { method: "POST", body: JSON.stringify(corpo) }),
  patch: (caminho, corpo) => chamar(caminho, { method: "PATCH", body: JSON.stringify(corpo) }),
  del: (caminho) => chamar(caminho, { method: "DELETE" }),
};

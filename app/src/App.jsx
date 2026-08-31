import { Suspense, lazy, useEffect, useState } from "react";
import "leaflet/dist/leaflet.css";
import "./App.css";
import LoginView from "./views/LoginView";
import VisitaEmAndamento from "./components/VisitaEmAndamento";
import { api, limparSessao, registrarAoExpirar, tokenSalvo, usuarioSalvo } from "./lib/api";

// Cada aba é baixada só quando aberta pela primeira vez. Antes, tudo vinha num
// pacote único de ~795 KB — incluindo a biblioteca de PDF, usada apenas no
// "Plano da Semana", que o vendedor pode nunca abrir. O login (tela que todo
// mundo vê primeiro) fica fora disso de propósito, para aparecer na hora.
const MapaView = lazy(() => import("./views/MapaView"));
const PlanoView = lazy(() => import("./views/PlanoView"));
const RotaDiaView = lazy(() => import("./views/RotaDiaView"));
const RelatoriosView = lazy(() => import("./views/RelatoriosView"));
const SugestoesVinculoView = lazy(() => import("./views/SugestoesVinculoView"));
const UsuariosView = lazy(() => import("./views/UsuariosView"));
const RelatorioVisita = lazy(() => import("./views/RelatorioVisita"));

const ABAS_BASE = ["Mapa", "Plano da Semana", "Rota do Dia", "Relatórios", "Carteira"];

export default function App() {
  const [aba, setAba] = useState("Mapa");
  const [clientes, setClientes] = useState(null);
  const [logoOk, setLogoOk] = useState(true);
  const [usuario, setUsuario] = useState(() => (tokenSalvo() ? usuarioSalvo() : null));
  const [erroCarga, setErroCarga] = useState("");
  const [visitaPendente, setVisitaPendente] = useState(null);
  // nome do cliente da visita aberta — a visita só traz o id, e a barra
  // precisa dizer ONDE a visita está aberta pra ser útil em campo
  const [nomeClienteVisita, setNomeClienteVisita] = useState("");
  const [visitasHojeIds, setVisitasHojeIds] = useState(() => new Set());
  const [menuAberto, setMenuAberto] = useState(false);

  // sessão expirada em qualquer chamada -> volta pro login
  useEffect(() => {
    registrarAoExpirar(() => setUsuario(null));
  }, []);

  useEffect(() => {
    if (!usuario) return;
    setClientes(null);
    setErroCarga("");
    setAba("Mapa"); // troca de conta (ex.: admin -> vendedor) não deve manter aba restrita na tela
    setMenuAberto(false);
    api.get("/api/clientes")
      .then(setClientes)
      .catch((e) => { setClientes([]); setErroCarga(e.message); });
    // restaura o bloqueio se o app recarregou no meio de uma visita
    api.get("/api/visitas/pendente").then(setVisitaPendente).catch(() => {});
    api.get("/api/visitas/hoje").then((ids) => setVisitasHojeIds(new Set(ids))).catch(() => {});
  }, [usuario]);

  // O nome vem do servidor porque a lista carregada na tela pode não conter
  // esse cliente (ela é filtrada), e a barra sem nome não ajudaria ninguém.
  useEffect(() => {
    if (!visitaPendente?.clienteId) {
      setNomeClienteVisita("");
      return;
    }
    let vivo = true;
    api.get(`/api/clientes/${visitaPendente.clienteId}`)
      .then((c) => { if (vivo) setNomeClienteVisita(c.nome); })
      .catch(() => { if (vivo) setNomeClienteVisita(""); });
    return () => { vivo = false; };
  }, [visitaPendente?.clienteId]);

  function sair() {
    limparSessao();
    setUsuario(null);
    setClientes(null);
    setVisitaPendente(null);
  }

  async function iniciarVisita(clienteId) {
    const visita = await api.post("/api/visitas", { clienteId });
    setVisitaPendente(visita);
    return visita;
  }

  async function finalizarVisita() {
    const atualizada = await api.patch(`/api/visitas/${visitaPendente.id}/finalizar`, {});
    setVisitaPendente(atualizada);
  }

  // Abandona a visita aberta. É a saída pra quem esqueceu de finalizar e
  // ficou impedido de abrir qualquer outra — o caso que travou o Taborda.
  async function cancelarVisita() {
    await api.del(`/api/visitas/${visitaPendente.id}`);
    setVisitaPendente(null);
  }

  // Reflete um PATCH de cliente na lista principal: some da lista se virou
  // inativo (a lista padrão do backend também exclui), some se voltar a
  // aparecer (reativado a partir da view de inativos).
  function atualizarClienteLocal(atualizado) {
    setClientes((lista) => {
      if (!lista) return lista;
      if (atualizado.status === "inativo") {
        return lista.filter((c) => c.id !== atualizado.id);
      }
      const existe = lista.some((c) => c.id === atualizado.id);
      return existe
        ? lista.map((c) => (c.id === atualizado.id ? atualizado : c))
        : [...lista, atualizado];
    });
  }

  if (!usuario) return <LoginView aoEntrar={setUsuario} />;

  const abas = usuario.papel === "admin" ? [...ABAS_BASE, "Vínculos", "Usuários"] : ABAS_BASE;

  return (
    <div className="app">
      <header className="nav">
        <div className="nav-inner">
          <div className="brand">
            {logoOk ? (
              <img
                src="/ppg-logo.webp"
                alt="PPG Parafusos e Ferramentas"
                className="brand-logo"
                onError={() => setLogoOk(false)}
              />
            ) : (
              <div className="brand-wordmark">
                <span>PPG</span>
                <small>Parafusos e Ferramentas</small>
              </div>
            )}
          </div>
          <nav className="tabs">
            {abas.map((t) => (
              <button key={t} className={"tab" + (aba === t ? " active" : "")} onClick={() => setAba(t)}>
                {t}
              </button>
            ))}
          </nav>
          <button
            className="btn-hamburguer"
            onClick={() => setMenuAberto((v) => !v)}
            aria-label="Abrir menu"
            aria-expanded={menuAberto}
          >
            <span /><span /><span />
          </button>
          <div className="nav-right">
            <span className="muted nav-contador" style={{ fontSize: 13 }}>
              {clientes ? `${clientes.length.toLocaleString("pt-BR")} clientes` : "carregando…"}
            </span>
            <span className="muted nav-usuario" style={{ fontSize: 13 }}>· {usuario.nome}</span>
            <button className="btn-sair" onClick={sair} title="Sair da conta">Sair</button>
          </div>
        </div>

        {menuAberto && (
          <nav className="tabs-mobile">
            {abas.map((t) => (
              <button
                key={t}
                className={"tab-mobile" + (aba === t ? " active" : "")}
                onClick={() => { setAba(t); setMenuAberto(false); }}
              >
                {t}
              </button>
            ))}
            <div className="tabs-mobile-rodape muted">{usuario.nome}</div>
          </nav>
        )}
      </header>

      {/* Enquanto houver visita aberta, ela fica visível em qualquer tela —
          com onde está aberta e como sair dela. Antes, essa informação só
          existia dentro da ficha do cliente certo: quem não soubesse qual era
          ficava sem conseguir abrir nenhuma visita nova, sem nada na tela
          explicando por quê. */}
      {visitaPendente?.status === "aberta" && (
        <VisitaEmAndamento
          visita={visitaPendente}
          nomeCliente={nomeClienteVisita}
          aoFinalizar={finalizarVisita}
          aoCancelar={cancelarVisita}
        />
      )}

      <main className="conteudo">
        <Suspense fallback={<div className="vazio">Carregando…</div>}>
        {!clientes ? (
          <div className="vazio">
            {erroCarga ? (
              <>
                <p>Não foi possível carregar a carteira.</p>
                <p className="muted" style={{ fontSize: 13 }}>{erroCarga}</p>
              </>
            ) : (
              "Carregando carteira…"
            )}
          </div>
        ) : aba === "Mapa" ? (
          <MapaView
            clientes={clientes}
            aoAtualizarCliente={atualizarClienteLocal}
            visitaPendente={visitaPendente}
            aoIniciarVisita={iniciarVisita}
            aoFinalizarVisita={finalizarVisita}
            aoCancelarVisita={cancelarVisita}
            usuario={usuario}
          />
        ) : aba === "Plano da Semana" ? (
          <PlanoView clientes={clientes} usuario={usuario} aoAbrirRotaDoDia={() => setAba("Rota do Dia")} />
        ) : aba === "Rota do Dia" ? (
          <RotaDiaView
            aoAtualizarCliente={atualizarClienteLocal}
            visitaPendente={visitaPendente}
            aoIniciarVisita={iniciarVisita}
            aoFinalizarVisita={finalizarVisita}
            aoCancelarVisita={cancelarVisita}
            visitasHojeIds={visitasHojeIds}
            usuario={usuario}
          />
        ) : aba === "Relatórios" ? (
          <RelatoriosView usuario={usuario} />
        ) : aba === "Vínculos" ? (
          <SugestoesVinculoView />
        ) : aba === "Usuários" ? (
          <UsuariosView usuarioAtual={usuario} />
        ) : (
          <div className="vazio">
            <h3>{aba}</h3>
            <p className="muted">Em construção — próxima etapa.</p>
          </div>
        )}
        </Suspense>
      </main>

      {/* Modal bloqueante: aparece assim que a visita é finalizada e trava
          o app inteiro até o relatório ser salvo — não tem botão de fechar. */}
      {visitaPendente?.status === "aguardando_relatorio" && (
        <Suspense fallback={<div className="vazio">Abrindo o relatório da visita…</div>}>
          <RelatorioVisita
            visita={visitaPendente}
            aoSalvo={() => {
              setVisitasHojeIds((s) => new Set(s).add(visitaPendente.clienteId));
              setVisitaPendente(null);
            }}
          />
        </Suspense>
      )}
    </div>
  );
}

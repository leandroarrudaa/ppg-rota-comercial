import { useEffect, useMemo, useRef, useState } from "react";
import { MapContainer, TileLayer, Marker, Polyline, Popup, Tooltip, useMap, useMapEvents } from "react-leaflet";
import L from "leaflet";
import { api } from "../lib/api";
import { valorEstrategico, vizinhoMaisProximo, rotaEstrada, motivoVisita } from "../lib/rota";
import { FAIXAS, FAIXA_COR, FAIXA_CHIP, FAIXA_DOT, brl, num, telefoneFmt } from "../lib/format";
import MapAutoSize from "../components/MapAutoSize";
import FichaCliente from "./FichaCliente";

const FXKEY = { Ouro: "gold", Prata: "silver", Bronze: "bronze" };

// Observa o viewport do mapa (pan/zoom) e reporta o bbox atual pro pai —
// é o "raio de seleção" da Rota do Dia: o que está visível na tela, não um
// círculo geométrica (decisão explícita do usuário) — a busca por nome,
// porém, vale pra carteira inteira (decisão explícita separada).
function ObservarViewport({ aoMudar, visivel }) {
  // ref (não state) pra sempre ler o valor mais recente dentro dos handlers
  // do Leaflet, que não são recriados a cada render.
  const visivelRef = useRef(visivel);
  useEffect(() => { visivelRef.current = visivel; }, [visivel]);

  const map = useMapEvents({
    moveend: () => reportar(),
    zoomend: () => reportar(),
  });
  function reportar() {
    // com o mapa escondido (modo filtro no mobile) o container fica 0x0 —
    // um resize da janela (ex.: teclado abrindo pra digitar um filtro) pode
    // disparar invalidateSize/moveend mesmo assim, lendo limites inválidos e
    // zerando a lista bem na hora em que o usuário mexe num filtro. Ignora
    // qualquer leitura de limites enquanto o mapa não está de fato visível.
    if (!visivelRef.current) return;
    const b = map.getBounds();
    aoMudar([b.getSouth(), b.getWest(), b.getNorth(), b.getEast()]);
  }
  useEffect(() => { reportar(); }, []); // primeira leitura ao montar
  // No mobile o mapa pode começar escondido (modo filtro) e só ganhar
  // tamanho real quando o usuário troca pra "Ver mapa" — sem isso, os
  // limites lidos no mount são de um container 0x0 e a busca por bbox
  // nunca acha ninguém. Revalida toda vez que ele fica visível de novo —
  // mas não na primeira vez (o efeito de mount logo acima já cobre isso;
  // sem esse guard, toda tela abria disparando 2 buscas idênticas em vez de 1).
  const primeiraVezRef = useRef(true);
  useEffect(() => {
    if (!visivel) return;
    if (primeiraVezRef.current) { primeiraVezRef.current = false; return; }
    const t = setTimeout(() => { map.invalidateSize(); reportar(); }, 260);
    return () => clearTimeout(t);
  }, [visivel]);
  return null;
}

function pinNumerado(n, cor, emRisco) {
  const borda = emRisco ? "3px solid #e8543f" : "2px solid #fff";
  return L.divIcon({
    className: "",
    html: `<div class="pin-num" style="background:${cor};border:${borda}">${n}</div>`,
    iconSize: [26, 26],
    iconAnchor: [13, 13],
  });
}

function FitRota({ pontos }) {
  const map = useMap();
  useEffect(() => {
    if (!pontos.length) return;
    const lats = pontos.map((p) => p.lat);
    const lngs = pontos.map((p) => p.lng);
    map.fitBounds([[Math.min(...lats), Math.min(...lngs)], [Math.max(...lats), Math.max(...lngs)]], { padding: [60, 60], maxZoom: 15 });
  }, [pontos]);
  return null;
}

export default function RotaDiaView({ aoAtualizarCliente, visitaPendente, aoIniciarVisita, aoFinalizarVisita, visitasHojeIds, usuario }) {
  const [bbox, setBbox] = useState(null);
  const [candidatosBbox, setCandidatosBbox] = useState([]);
  const [carregando, setCarregando] = useState(false);

  const [buscaTexto, setBuscaTexto] = useState("");
  const [candidatosBusca, setCandidatosBusca] = useState(null); // null = sem busca ativa
  const [buscando, setBuscando] = useState(false);

  const [faixasOn, setFaixasOn] = useState({ Ouro: true, Prata: true, Bronze: true });
  const [soRisco, setSoRisco] = useState(false);
  const [faturamentoMin, setFaturamentoMin] = useState(0);
  // Só importa no mobile (CSS): faturamento/faixa/risco recolhidos por
  // padrão pra sobrar mais espaço de tela pra lista de clientes, que é o
  // que se usa o tempo todo — no desktop esses filtros continuam sempre
  // visíveis, independente desse estado.
  const [filtrosAbertos, setFiltrosAbertos] = useState(false);

  const [selecionados, setSelecionados] = useState(() => new Set());
  const [conhecidos, setConhecidos] = useState(() => new Map()); // id -> cliente, acumulado de bbox+busca
  const [modo, setModo] = useState("selecionando"); // selecionando | rota
  const [rota, setRota] = useState(null); // { ordem, estrada }
  const [carregandoRota, setCarregandoRota] = useState(false);
  const [fichaAberta, setFichaAberta] = useState(null); // cliente selecionado, ou null
  const [finalizando, setFinalizando] = useState(false);
  // Só importa em telas pequenas: no mobile painel e mapa não cabem juntos,
  // então alterna qual ocupa a tela. Diferente do Mapa (que começa no
  // filtro): aqui a lista de clientes DEPENDE da área visível do mapa, então
  // precisa começar com o mapa visível — senão abre sempre zerado.
  const [modoMobile, setModoMobile] = useState("mapa");
  const mapRef = useRef(null);
  const bboxAtualRef = useRef(null);

  function abrirFicha(cliente) {
    setFichaAberta(cliente);
  }
  function atualizarFicha(atualizado) {
    setFichaAberta(atualizado);
    aoAtualizarCliente(atualizado);
    setCandidatosBbox((lista) => lista.map((c) => (c.id === atualizado.id ? atualizado : c)));
    setCandidatosBusca((lista) => lista && lista.map((c) => (c.id === atualizado.id ? atualizado : c)));
    setRota((r) => r && { ...r, ordem: r.ordem.map((c) => (c.id === atualizado.id ? atualizado : c)) });
    setConhecidos((mapa) => new Map(mapa).set(atualizado.id, atualizado));
  }

  // bbox — universo padrão de seleção (o que está visível no mapa)
  // zoom/arraste rápido dispara vários pedidos em sequência; sem esse guard,
  // uma resposta de um bbox mais antigo (mais largo) podia chegar depois da
  // resposta do bbox atual e sobrescrever com contagem/pinos de outra região.
  useEffect(() => {
    if (!bbox) return;
    setCarregando(true);
    bboxAtualRef.current = bbox;
    const meuBbox = bbox;
    const [minLat, minLng, maxLat, maxLng] = bbox;
    api.get(`/api/clientes?bbox=${minLat},${minLng},${maxLat},${maxLng}`)
      .then((dados) => { if (bboxAtualRef.current === meuBbox) setCandidatosBbox(dados); })
      .catch(() => { if (bboxAtualRef.current === meuBbox) setCandidatosBbox([]); })
      .finally(() => { if (bboxAtualRef.current === meuBbox) setCarregando(false); });
  }, [bbox]);

  // busca — carteira inteira, independente do que está visível no mapa
  // (decisão explícita: pesquisar um cliente não deve exigir que ele esteja na tela)
  useEffect(() => {
    const termo = buscaTexto.trim();
    if (termo.length < 2) { setCandidatosBusca(null); return; }
    setBuscando(true);
    const timer = setTimeout(() => {
      api.get(`/api/clientes?busca=${encodeURIComponent(termo)}&elegivelVisita=true`)
        .then(setCandidatosBusca)
        .catch(() => setCandidatosBusca([]))
        .finally(() => setBuscando(false));
    }, 300);
    return () => clearTimeout(timer);
  }, [buscaTexto]);

  // acumula tudo que já foi visto (bbox ou busca) pra gerarRota conseguir
  // resolver o cliente inteiro mesmo se ele saiu da lista exibida no momento
  useEffect(() => {
    setConhecidos((mapa) => {
      const novo = new Map(mapa);
      candidatosBbox.forEach((c) => novo.set(c.id, c));
      (candidatosBusca || []).forEach((c) => novo.set(c.id, c));
      return novo;
    });
  }, [candidatosBbox, candidatosBusca]);

  const buscaAtiva = buscaTexto.trim().length >= 2;
  const poolAtivo = buscaAtiva ? (candidatosBusca || []) : candidatosBbox;

  function passaFiltro(c) {
    if (c.origem === "antigo" && !faixasOn[c.faixa]) return false;
    if (c.origem === "antigo" && faturamentoMin > 0 && (c.fat || 0) < faturamentoMin) return false;
    if (soRisco && !c.emRisco) return false;
    return true;
  }

  const poolFiltrado = useMemo(() => poolAtivo.filter(passaFiltro), [poolAtivo, faixasOn, soRisco, faturamentoMin]);
  // os pinos do mapa também precisam respeitar o filtro — senão o mapa mostra
  // cor/faixa que a lista já escondeu, ficando incoerente com os contadores
  const bboxFiltrado = useMemo(() => candidatosBbox.filter(passaFiltro), [candidatosBbox, faixasOn, soRisco, faturamentoMin]);

  const antigos = useMemo(
    () => poolFiltrado.filter((c) => c.origem === "antigo").sort((a, b) => valorEstrategico(b) - valorEstrategico(a)),
    [poolFiltrado]
  );
  const novos = useMemo(
    () => poolFiltrado.filter((c) => c.origem === "novo").sort((a, b) => a.nome.localeCompare(b.nome)),
    [poolFiltrado]
  );

  function alternar(id) {
    setSelecionados((s) => {
      const novo = new Set(s);
      novo.has(id) ? novo.delete(id) : novo.add(id);
      return novo;
    });
  }

  async function gerarRota() {
    const escolhidos = [...selecionados].map((id) => conhecidos.get(id)).filter(Boolean);
    if (escolhidos.length === 0) return;
    const ordem = escolhidos.length > 1 ? vizinhoMaisProximo(escolhidos, escolhidos[0]) : escolhidos;
    setModo("rota");
    setRota({ ordem, estrada: null });
    if (ordem.length >= 2) {
      setCarregandoRota(true);
      try {
        const estrada = await rotaEstrada(ordem);
        setRota({ ordem, estrada });
      } catch {
        setRota({ ordem, estrada: null });
      } finally {
        setCarregandoRota(false);
      }
    }
  }

  function novaSelecao() {
    setModo("selecionando");
    setRota(null);
    setSelecionados(new Set());
  }

  async function finalizarAqui() {
    setFinalizando(true);
    try {
      await aoFinalizarVisita();
    } finally {
      setFinalizando(false);
    }
  }

  const ficha = fichaAberta && (
    <FichaCliente
      cliente={fichaAberta}
      aoFechar={() => setFichaAberta(null)}
      aoAtualizar={atualizarFicha}
      visitaPendente={visitaPendente}
      aoIniciarVisita={aoIniciarVisita}
      aoFinalizarVisita={aoFinalizarVisita}
      usuario={usuario}
    />
  );

  if (modo === "rota" && rota) {
    const kmReta = rota.ordem.length > 1
      ? rota.ordem.slice(1).reduce((s, c, i) => s + Math.hypot(c.lat - rota.ordem[i].lat, c.lng - rota.ordem[i].lng) * 111, 0)
      : 0;
    const km = rota.estrada ? rota.estrada.km : kmReta * 1.35;
    const min = rota.estrada ? rota.estrada.min : (kmReta * 1.35) / 0.6;
    const linha = rota.estrada ? rota.estrada.linha : rota.ordem.map((c) => [c.lat, c.lng]);
    return (
      <div className={"mapa-layout rota-dia-layout" + (modoMobile === "mapa" ? " modo-mapa-mobile" : " modo-painel-mobile")}>
        <button
          type="button"
          className="btn-alternar-mobile"
          onClick={() => setModoMobile((m) => (m === "mapa" ? "painel" : "mapa"))}
        >
          {modoMobile === "mapa" ? "☰ Ver filtros" : "🗺️ Ver mapa"}
        </button>
        <aside className="painel">
          <div className="painel-head">
            <h3>Rota do dia</h3>
            <p className="muted" style={{ fontSize: 13 }}>{rota.ordem.length} clientes selecionados</p>
          </div>
          <div className="resumo">
            <div className="resumo-item"><span>Distância</span><b>{km.toFixed(0)} km {carregandoRota && <small className="faint">…</small>}</b></div>
            <div className="resumo-item"><span>Tempo em rota</span><b>{Math.floor(min / 60)}h{String(Math.round(min % 60)).padStart(2, "0")}</b></div>
          </div>
          <div className="filtro-grupo">
            <span className="filtro-titulo">Ordem de visita</span>
            <ol className="rota-lista">
              {rota.ordem.map((c, i) => {
                const emAndamento = visitaPendente?.clienteId === c.id;
                const jaVisitado = visitasHojeIds?.has(c.id);
                return (
                  <li
                    key={c.id}
                    className={"rota-item" + (jaVisitado ? " rota-item-visitado" : "")}
                    onClick={() => !emAndamento && abrirFicha(c)}
                  >
                    <span className="ordem-num" style={{ background: FAIXA_COR[c.faixa] || "#8e949b" }}>{i + 1}</span>
                    <div className="rota-info">
                      <div className="rota-nome">
                        {c.nome} {c.temPromessaPendente && <span title="Tem promessa pendente">🎁</span>}
                      </div>
                      <div className="faint" style={{ fontSize: 12 }}>{c.bairro || c.cidade} · {c.faixa ? brl(c.fat) : "cliente novo"}</div>
                      {emAndamento && (
                        <button
                          className="btn btn-primary"
                          style={{ marginTop: 6, fontSize: 12, padding: "4px 10px" }}
                          onClick={(e) => { e.stopPropagation(); finalizarAqui(); }}
                          disabled={finalizando}
                        >
                          {finalizando ? "Finalizando…" : "Finalizar visita"}
                        </button>
                      )}
                    </div>
                  </li>
                );
              })}
            </ol>
          </div>
          <button className="btn btn-ghost" style={{ width: "100%", justifyContent: "center" }} onClick={novaSelecao}>
            ← Nova seleção
          </button>
        </aside>
        <div className="mapa-wrap">
          <MapContainer center={[rota.ordem[0].lat, rota.ordem[0].lng]} zoom={13} style={{ height: "100%", width: "100%" }}>
            <TileLayer url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png" attribution="&copy; OpenStreetMap &copy; CARTO" subdomains="abcd" />
            <MapAutoSize />
            <FitRota pontos={rota.ordem} />
            <Polyline positions={linha} pathOptions={{ color: "#0a0a0b", weight: 4, opacity: 0.65 }} />
            {rota.ordem.map((c, i) => (
              <Marker key={c.id} position={[c.lat, c.lng]} icon={pinNumerado(i + 1, FAIXA_COR[c.faixa] || "#8e949b", c.emRisco)}>
                <Popup>
                  <b>{i + 1}. {c.nome}</b><br />
                  {c.faixa ? `${c.faixa} · ${brl(c.fat)} · ${motivoVisita(c)}` : "Cliente novo"}
                </Popup>
              </Marker>
            ))}
          </MapContainer>
        </div>
        {ficha}
      </div>
    );
  }

  return (
    <div className={"mapa-layout rota-dia-layout" + (modoMobile === "mapa" ? " modo-mapa-mobile" : " modo-painel-mobile")}>
      <button
        type="button"
        className="btn-alternar-mobile"
        onClick={() => setModoMobile((m) => (m === "mapa" ? "painel" : "mapa"))}
      >
        {modoMobile === "mapa" ? "☰ Ver filtros" : "🗺️ Ver mapa"}
      </button>
      <aside className="painel rota-dia-painel">
        <div className="painel-head">
          <h3>Rota do dia</h3>
          <p className="muted" style={{ fontSize: 13 }}>
            Dê zoom/arraste o mapa pra ver os clientes da região, ou busque um cliente específico em qualquer lugar da carteira.
          </p>
        </div>

        <div className="field search">
          <svg className="search-ico" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
            <circle cx="11" cy="11" r="7" /><line x1="21" y1="21" x2="16.7" y2="16.7" />
          </svg>
          <input
            className="input input-search"
            placeholder="Buscar cliente (toda a carteira)…"
            value={buscaTexto}
            onChange={(e) => setBuscaTexto(e.target.value)}
          />
        </div>

        <button
          type="button"
          className="btn-toggle-filtros"
          onClick={() => setFiltrosAbertos((v) => !v)}
        >
          {filtrosAbertos ? "▲ Menos filtros" : "▾ Mais filtros (faturamento, faixa, risco)"}
        </button>

        <div className={"rota-dia-filtros-extra" + (filtrosAbertos ? " aberto" : "")}>
          <div className="filtro-grupo">
            <span className="filtro-titulo">Faturamento mínimo</span>
            <input
              className="input"
              type="number"
              min="0"
              step="1000"
              placeholder="Ex: 30000"
              value={faturamentoMin || ""}
              onChange={(e) => setFaturamentoMin(Number(e.target.value) || 0)}
            />
            {faturamentoMin > 0 && (
              <p className="muted" style={{ fontSize: 12, marginTop: 2 }}>
                Só clientes antigos com faturamento acima de {brl(faturamentoMin)}
              </p>
            )}
          </div>

          <div className="filtro-grupo">
            <span className="filtro-titulo">Faixa RFM</span>
            <div className="medais">
              {FAIXAS.map((f) => {
                const k = FXKEY[f];
                return (
                  <button
                    key={f}
                    className={"medal medal-" + k + (faixasOn[f] ? "" : " off")}
                    onClick={() => setFaixasOn((s) => ({ ...s, [f]: !s[f] }))}
                    aria-pressed={faixasOn[f]}
                  >
                    <span className={"coin coin-" + k} />
                    <span className="medal-body">
                      <span className="medal-top">
                        <span className="medal-name">{f}</span>
                        <span className="medal-count">{num(antigos.filter((c) => c.faixa === f).length)}</span>
                      </span>
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          <button
            className={"risco-card" + (soRisco ? " on" : "")}
            onClick={() => setSoRisco((v) => !v)}
            aria-pressed={soRisco}
          >
            <span className="risco-pulse" />
            <span className="risco-body">
              <span className="risco-label">Só clientes em risco</span>
            </span>
          </button>
        </div>

        <button className="btn btn-primary" style={{ width: "100%", justifyContent: "center" }} disabled={selecionados.size === 0} onClick={gerarRota}>
          Gerar rota ({selecionados.size})
        </button>

        <div className="rota-dia-colunas">
          <div className="rota-dia-coluna">
            <span className="filtro-titulo">Clientes antigos {(carregando || buscando) ? "" : `(${antigos.length})`}</span>
            {(buscaAtiva ? buscando : carregando) ? <p className="muted" style={{ fontSize: 13 }}>Carregando…</p> : antigos.length === 0 ? (
              <p className="muted" style={{ fontSize: 13 }}>{buscaAtiva ? "Nenhum resultado." : "Nenhum nessa área."}</p>
            ) : antigos.map((c) => (
              <label key={c.id} className="rota-dia-item" title={`${c.nome} · ${brl(c.fat)}`}>
                <input type="checkbox" checked={selecionados.has(c.id)} onChange={() => alternar(c.id)} />
                <span className={"chip " + FAIXA_CHIP[c.faixa]}><span className={"dot " + FAIXA_DOT[c.faixa]} /></span>
                <span className="rota-dia-nome">{c.nome}</span>
                <span className="rota-dia-fat faint">{brl(c.fat)}</span>
                {c.temPromessaPendente && <span title="Tem promessa pendente">🎁</span>}
              </label>
            ))}
          </div>
          <div className="rota-dia-coluna">
            <span className="filtro-titulo">Clientes novos {(carregando || buscando) ? "" : `(${novos.length})`}</span>
            {novos.length === 0 ? (
              <p className="muted" style={{ fontSize: 13 }}>{buscaAtiva ? "Nenhum resultado." : "Sem clientes novos cadastrados ainda."}</p>
            ) : novos.map((c) => (
              <label key={c.id} className="rota-dia-item">
                <input type="checkbox" checked={selecionados.has(c.id)} onChange={() => alternar(c.id)} />
                <span className="rota-dia-nome">{c.nome}</span>
                {c.temPromessaPendente && <span title="Tem promessa pendente">🎁</span>}
              </label>
            ))}
          </div>
        </div>
      </aside>

      <div className="mapa-wrap">
        <MapContainer ref={mapRef} center={[-25.095, -50.16]} zoom={12} preferCanvas style={{ height: "100%", width: "100%" }}>
          <TileLayer url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png" attribution="&copy; OpenStreetMap &copy; CARTO" subdomains="abcd" />
          <MapAutoSize />
          <ObservarViewport aoMudar={setBbox} visivel={modoMobile === "mapa"} />
          {bboxFiltrado.map((c) => (
            <Marker
              key={c.id}
              position={[c.lat, c.lng]}
              icon={pinNumerado(selecionados.has(c.id) ? "✓" : "", selecionados.has(c.id) ? "#1e8e5a" : (FAIXA_COR[c.faixa] || "#8e949b"), c.emRisco)}
              eventHandlers={{ click: () => alternar(c.id) }}
            >
              {/* Tooltip (hover) em vez de Popup (clique): um balão de clique
                  competia com o clique de selecionar/desselecionar — cobria
                  marcadores vizinhos e o autoPan do Leaflet movia o mapa
                  sozinho, disparando buscas em cascata. */}
              <Tooltip>
                <b>{c.nome}</b><br />
                {c.faixa || "Novo"} {c.faixa ? `· ${brl(c.fat)}` : ""} {c.telefone ? `· ${telefoneFmt(c.telefone)}` : ""}
              </Tooltip>
            </Marker>
          ))}
        </MapContainer>
      </div>
      {ficha}
    </div>
  );
}

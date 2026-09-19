import { useEffect, useMemo, useRef, useState } from "react";
import { MapContainer, TileLayer, Marker, Polyline, Popup, useMap } from "react-leaflet";
import L from "leaflet";
import {
  montarPlanoSemana, otimizarRotaEstrada, vizinhoMaisProximo, refinar2opt, distKm, kmTotalReta,
  motivoVisita, textoAgenda, estaNaHoraDeVisitar, DIAS,
} from "../lib/rota";
import { recomendar } from "../lib/recomendacao";
import { gerarPdfDia } from "../lib/pdf";
import { usarRotaExterna } from "../lib/rotaSalva";
import { api } from "../lib/api";
import { corDoCliente, brl, telefoneFmt, recenciaTexto } from "../lib/format";
import MapAutoSize from "../components/MapAutoSize";
import ChipFaixa from "../components/ChipFaixa";

function pinNumerado(n, cor, risco) {
  return L.divIcon({
    className: "",
    html: `<div class="pin-num" style="background:${cor};${risco ? "box-shadow:0 0 0 3px #e8543f;" : ""}">${n}</div>`,
    iconSize: [26, 26],
    iconAnchor: [13, 13],
  });
}

// Pino cinza/transparente de quem está perto da rota mas não entrou no
// plano — só pra dar visibilidade e permitir adicionar com um toque, sem
// competir visualmente com a numeração da rota escolhida.
function pinFantasma() {
  return L.divIcon({
    className: "",
    html: `<div class="pin-fantasma"></div>`,
    iconSize: [16, 16],
    iconAnchor: [8, 8],
  });
}

function FitRota({ pontos }) {
  const map = useMap();
  useEffect(() => {
    if (!pontos.length) return;
    const lats = pontos.map((p) => p.lat);
    const lngs = pontos.map((p) => p.lng);
    map.fitBounds(
      [[Math.min(...lats), Math.min(...lngs)], [Math.max(...lats), Math.max(...lngs)]],
      { padding: [60, 60], maxZoom: 15 }
    );
  }, [pontos]);
  return null;
}

export default function VisitasView({ clientes, usuario, aoAbrirRotaDoDia }) {
  const [capacidade, setCapacidade] = useState(12);
  const [dia, setDia] = useState(0);
  // Por padrão o plano só traz quem está na hora de visitar. A chave existe
  // para completar um dia fraco — não para voltar ao comportamento antigo.
  const [incluirNaoVencidos, setIncluirNaoVencidos] = useState(false);
  const [estrada, setEstrada] = useState(null);
  // Ordem final da rota: começa igual a plano.clientes (linha reta, já com
  // 2-opt — ver montarPlanoSemana) e é substituída pela ordem de estrada
  // real assim que o OSRM responde (ver efeito abaixo). Guardada à parte
  // porque plano.clientes vem de um useMemo — não dá pra "corrigir" esse
  // array depois que a resposta assíncrona chega.
  const [ordemFinal, setOrdemFinal] = useState(null);
  const [carregandoRota, setCarregandoRota] = useState(false);
  const [aberto, setAberto] = useState(null);
  // Só importa no mobile (CSS): dia/capacidade/resumo/PDF recolhidos por
  // padrão pra sobrar tela pra lista de visitas, que é o que se usa o tempo
  // todo — no desktop esses controles continuam sempre visíveis. Mesma ideia
  // pro toggle painel/mapa: no celular os dois espremidos juntos ficam
  // pequenos demais pra usar (lista ilegível, mapa minúsculo).
  const [opcoesAbertas, setOpcoesAbertas] = useState(false);
  const [vizinhosAbertos, setVizinhosAbertos] = useState(false);
  const [modoMobile, setModoMobile] = useState("painel");
  // Raio de agrupamento do dia e peso da distância — configuráveis pelo
  // Admin em Ajustes (ver backend/app/services/configuracoes.py). Os
  // valores abaixo são o padrão de fábrica, usados até a config chegar (ou
  // se a busca falhar — nunca trava o plano por causa disso).
  const [config, setConfig] = useState({ raioDiaKm: 45, penalidadeKm: 3 });
  // Ajuste manual em cima do plano automático: quem o algoritmo escolheu mas
  // o vendedor tirou (removidosIds), e quem estava por perto e ele decidiu
  // incluir (extras) — ver vizinhosProximos/adicionar/remover abaixo.
  // Zerados toda vez que o plano do dia muda (ver efeito mais abaixo).
  const [removidosIds, setRemovidosIds] = useState(() => new Set());
  const [extras, setExtras] = useState([]);
  const mapRef = useRef(null);
  const markerRefs = useRef({});

  useEffect(() => {
    api.get("/api/configuracoes")
      .then((lista) => {
        const porChave = Object.fromEntries(lista.map((o) => [o.chave, o.valor]));
        setConfig({
          raioDiaKm: porChave.raio_dia_km ?? 45,
          penalidadeKm: porChave.penalidade_km ?? 3,
        });
      })
      .catch(() => {}); // fica valendo o padrão de fábrica
  }, []);

  // centraliza no pin e abre o balão (usado ao clicar no nome da lista)
  function focar(c) {
    const map = mapRef.current;
    if (map) map.setView([c.lat, c.lng], Math.max(map.getZoom(), 14), { animate: true });
    const mk = markerRefs.current[c.id];
    if (mk) mk.openPopup();
  }

  // Leva o plano deste dia pra Rota do Dia, pronto pra executar (abrir
  // visita, fechar com relatório) — em vez de fazer o Taborda selecionar os
  // mesmos clientes de novo na mão. Substitui a seleção que já estivesse
  // salva lá (não há perda real: visitas em andamento continuam finalizáveis
  // pela ficha do cliente, independente de qual lista está na tela).
  function usarHoje() {
    usarRotaExterna(usuario.id, ordemFinal || plano.clientes);
    aoAbrirRotaDoDia();
  }

  const planos = useMemo(
    () => montarPlanoSemana(clientes, capacidade, 5, incluirNaoVencidos, config),
    [clientes, capacidade, incluirNaoVencidos, config]
  );
  // quantos ficaram de fora só por terem sido visitados há pouco
  const aguardando = useMemo(
    () => clientes.filter((c) => c.lat != null && !estaNaHoraDeVisitar(c)).length,
    [clientes]
  );
  const plano = planos[dia] || planos[0];

  // Zera os ajustes manuais (quem foi tirado, quem foi adicionado) sempre
  // que o plano do dia muda — trocar de dia, capacidade ou filtro monta um
  // plano novo do zero; carregar ajuste de outro contexto pra ele não faz
  // sentido.
  useEffect(() => {
    setRemovidosIds(new Set());
    setExtras([]);
  }, [plano]);

  // Quem o vendedor quer visitar hoje: o plano automático, menos quem ele
  // tirou, mais quem ele adicionou pelos pinos cinza perto da rota — ainda
  // sem ordem nenhuma (isso é o efeito logo abaixo).
  const stopsDesejados = useMemo(() => {
    if (!plano) return [];
    const mantidos = plano.clientes.filter((c) => !removidosIds.has(c.id));
    const idsMantidos = new Set(mantidos.map((c) => c.id));
    return [...mantidos, ...extras.filter((c) => !idsMantidos.has(c.id))];
  }, [plano, removidosIds, extras]);

  // Roda de novo toda vez que MUDA QUEM vai (dia/capacidade/filtro trocando
  // o plano, ou um ajuste manual de adicionar/tirar) — nunca só por causa
  // da ordem interna mudar, senão a resposta do OSRM disparava o efeito de
  // novo e entrava em loop. A ordem em linha reta (2-opt) já aparece na
  // hora; a chamada ao OSRM só melhora ordem/distância quando responder —
  // se falhar, fica valendo a de linha reta, que já estava na tela.
  useEffect(() => {
    let vivo = true;
    setEstrada(null);
    if (stopsDesejados.length < 2) {
      setOrdemFinal(stopsDesejados);
      return;
    }
    const inicio = stopsDesejados.find((c) => c.id === plano?.seed?.id) || stopsDesejados[0];
    const ordemReta = refinar2opt(vizinhoMaisProximo(stopsDesejados, inicio));
    setOrdemFinal(ordemReta);
    setCarregandoRota(true);
    otimizarRotaEstrada(ordemReta)
      .then((r) => {
        if (!vivo || !r) return;
        setEstrada({ km: r.km, min: r.min, linha: r.linha });
        setOrdemFinal(r.ordem);
      })
      .catch(() => {})
      .finally(() => vivo && setCarregandoRota(false));
    return () => { vivo = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stopsDesejados]);

  // Adicionar/tirar clientes da rota do dia — usado pelos pinos do mapa
  // (fantasma = adicionar; numerado = tirar, dentro do próprio balão).
  function adicionar(cliente) {
    setExtras((lista) => (lista.some((c) => c.id === cliente.id) ? lista : [...lista, cliente]));
    setRemovidosIds((s) => {
      if (!s.has(cliente.id)) return s;
      const novo = new Set(s);
      novo.delete(cliente.id);
      return novo;
    });
  }
  function remover(cliente) {
    setExtras((lista) => lista.filter((c) => c.id !== cliente.id));
    setRemovidosIds((s) => new Set(s).add(cliente.id));
  }
  function desfazerAjustes() {
    setRemovidosIds(new Set());
    setExtras([]);
  }
  const temAjusteManual = removidosIds.size > 0 || extras.length > 0;

  if (!plano) {
    return (
      <div className="vazio">
        {aguardando > 0 ? (
          <>
            <p>Nenhum cliente vencido para visitar.</p>
            <p className="muted" style={{ fontSize: 13 }}>
              {aguardando} {aguardando === 1 ? "cliente foi visitado" : "clientes foram visitados"} há
              pouco e ainda não chegou a hora de voltar.
            </p>
            <button className="btn btn-ghost" style={{ marginTop: 12 }} onClick={() => setIncluirNaoVencidos(true)}>
              Incluir quem ainda não venceu
            </button>
          </>
        ) : (
          "Nenhum cliente ativo para visitar neste período."
        )}
      </div>
    );
  }

  const ordem = ordemFinal || plano.clientes;
  // kmReta do plano original só vale enquanto não há ajuste manual — com
  // adição/remoção, o total tem que ser recalculado em cima da ordem atual.
  const kmRetaAtual = temAjusteManual ? kmTotalReta(ordem) : plano.kmReta;
  const km = estrada ? estrada.km : kmRetaAtual * 1.35;
  const min = estrada ? estrada.min : (kmRetaAtual * 1.35) / 0.6;
  const linha = estrada ? estrada.linha : ordem.map((c) => [c.lat, c.lng]);
  const valorRoteiro = ordem.reduce((s, c) => s + (c.fat || 0), 0);

  // Quem está perto da rota de hoje mas não entrou no plano — pinos cinza
  // no mapa, pra dar visibilidade e deixar o vendedor incluir com um toque
  // se achar que vale a pena o desvio. Raio curto de propósito (é "já que
  // vou passar do lado", não "monta outro dia inteiro aqui").
  // Não é useMemo de propósito: já estamos depois do "if (!plano) return"
  // lá em cima, e um hook chamado só às vezes quebra a regra dos hooks. O
  // cálculo é barato (algumas dezenas de milhares de comparações de
  // distância no pior caso) — não pesa recalcular a cada render.
  const RAIO_VIZINHOS_KM = 6;
  const idsNaRota = new Set(ordem.map((c) => c.id));
  const vizinhosProximos = clientes
    // geo=="cidade" = geocodificador caiu no centro da cidade (endereço não
    // achado); mostrar esses como "perto da rota" seria mentira — todos
    // caem no mesmo ponto, não estão perto de nada de verdade (ver
    // montarPlanoSemana em lib/rota.js, mesmo motivo).
    .filter((c) => c.lat != null && c.geo !== "cidade" && !idsNaRota.has(c.id))
    .map((c) => ({ c, dist: Math.min(...ordem.map((p) => distKm(p, c))) }))
    .filter((x) => x.dist <= RAIO_VIZINHOS_KM)
    .sort((a, b) => a.dist - b.dist)
    .slice(0, 40);

  return (
    <div className={"mapa-layout" + (modoMobile === "mapa" ? " modo-mapa-mobile" : " modo-painel-mobile")}>
      <button
        type="button"
        className="btn-alternar-mobile"
        onClick={() => setModoMobile((m) => (m === "mapa" ? "painel" : "mapa"))}
      >
        {modoMobile === "mapa" ? "☰ Ver lista" : "🗺️ Ver mapa"}
      </button>

      <aside className="painel">
        <div className="painel-head">
          <h3>Plano de visitas</h3>
          <p className="muted" style={{ fontSize: 13 }}>Rota presencial · valor + economia</p>
        </div>

        <button
          type="button"
          className="btn-toggle-filtros"
          onClick={() => setOpcoesAbertas((v) => !v)}
        >
          {opcoesAbertas
            ? "▲ Menos opções"
            : `▾ ${DIAS[dia]} · ${capacidade}/dia · ${brl(valorRoteiro)}`}
        </button>

        <div className={"visitas-opcoes-extra" + (opcoesAbertas ? " aberto" : "")}>
          <div className="dias">
            {DIAS.map((d, i) => (
              <button key={d} className={"dia-btn" + (i === dia ? " on" : "")} onClick={() => setDia(i)}>
                {d.slice(0, 3)}
              </button>
            ))}
          </div>

          <div className="filtro-grupo">
            <span className="filtro-titulo">Visitas por dia: <b>{capacidade}</b></span>
            <input type="range" min="5" max="25" value={capacidade} onChange={(e) => setCapacidade(+e.target.value)} className="slider" />
          </div>

          {aguardando > 0 && (
            <label className="agenda-chave">
              <input
                type="checkbox"
                checked={incluirNaoVencidos}
                onChange={(e) => setIncluirNaoVencidos(e.target.checked)}
              />
              <span>
                Incluir quem ainda não venceu
                <small className="faint">
                  {" · "}{aguardando === 1
                    ? "1 visitado há pouco está de fora"
                    : `${aguardando} visitados há pouco estão de fora`}
                </small>
              </span>
            </label>
          )}

          <div className="resumo">
            <div className="resumo-item"><span>Visitas</span><b>{ordem.length}</b></div>
            <div className="resumo-item"><span>Distância</span><b>{km.toFixed(0)} km {carregandoRota && <small className="faint">…</small>}</b></div>
            <div className="resumo-item"><span>Tempo em rota</span><b>{Math.floor(min / 60)}h{String(Math.round(min % 60)).padStart(2, "0")}</b></div>
            <div className="resumo-item destaque"><span>Faturamento do roteiro</span><b>{brl(valorRoteiro)}</b></div>
          </div>

          {temAjusteManual && (
            <button type="button" className="btn btn-ghost" style={{ width: "100%", justifyContent: "center" }} onClick={desfazerAjustes}>
              ↺ Desfazer ajustes manuais
            </button>
          )}

          {aoAbrirRotaDoDia && usuario && (
            <button
              className="btn btn-primary"
              style={{ width: "100%", justifyContent: "center" }}
              onClick={usarHoje}
            >
              Usar esta rota hoje
            </button>
          )}

          <button
            className="btn btn-ghost"
            style={{ width: "100%", justifyContent: "center" }}
            onClick={() => gerarPdfDia({ diaNome: DIAS[dia], clientes: ordem, km, min, valor: valorRoteiro })}
          >
            Baixar PDF da rota
          </button>
        </div>

        <div className="filtro-grupo">
          <span className="filtro-titulo">Ordem de visita <span className="faint" style={{ textTransform: "none", fontWeight: 500 }}>· toque para ver a ação</span></span>
          <ol className="rota-lista">
            {ordem.map((c, i) => {
              const rec = recomendar(c);
              const open = aberto === c.id;
              return (
                <li key={c.id} className={"rota-item" + (open ? " aberto" : "")} onClick={() => { setAberto(open ? null : c.id); focar(c); }}>
                  <span className="ordem-num" style={{ background: corDoCliente(c) }}>{i + 1}</span>
                  <div className="rota-info">
                    <div className="rota-nome">{c.nome}</div>
                    <div className="rota-meta">
                      <ChipFaixa c={c} />
                      {c.emRisco && <span className="chip chip-risk"><span className="dot dot-risk" />risco</span>}
                    </div>
                    <div className="faint" style={{ fontSize: 12 }}>{c.bairro || c.cidade} · {c.faixa ? brl(c.fat) : "cliente novo"}</div>
                    <div className="faint" style={{ fontSize: 11 }}>{textoAgenda(c)}</div>
                    {open && (
                      <div className="rota-rec">
                        <b style={{ color: rec.cor }}>{rec.tag}</b>
                        <span>{rec.texto}</span>
                      </div>
                    )}
                  </div>
                  <button
                    type="button"
                    className="rota-item-remover"
                    title="Tirar da rota de hoje"
                    onClick={(e) => { e.stopPropagation(); remover(c); }}
                    disabled={ordem.length <= 1}
                  >
                    ×
                  </button>
                </li>
              );
            })}
          </ol>
        </div>

        {vizinhosProximos.length > 0 && (
          <div className="filtro-grupo">
            <button
              type="button"
              className="btn-toggle-vizinhos"
              onClick={() => setVizinhosAbertos((v) => !v)}
            >
              {vizinhosAbertos ? "▲ Esconder" : "▾"} Perto da rota de hoje <b>{vizinhosProximos.length}</b>
            </button>
            {vizinhosAbertos && (
              <ul className="vizinhos-lista">
                {vizinhosProximos.map(({ c, dist }) => (
                  <li key={c.id} className="vizinho-item">
                    <ChipFaixa c={c} semTexto />
                    <div className="vizinho-info">
                      <div className="vizinho-nome">{c.nome}</div>
                      <div className="faint" style={{ fontSize: 11 }}>{c.faixa ? brl(c.fat) : "cliente novo"} · a {dist.toFixed(1)} km da rota</div>
                    </div>
                    <button type="button" className="btn btn-ghost" onClick={() => adicionar(c)}>
                      + Incluir
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </aside>

      <div className="mapa-wrap">
        <MapContainer ref={mapRef} center={[-25.095, -50.16]} zoom={12} style={{ height: "100%", width: "100%" }}>
          <TileLayer url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png" attribution="&copy; OpenStreetMap &copy; CARTO" subdomains="abcd" />
          <MapAutoSize />
          <FitRota pontos={ordem} />
          <Polyline positions={linha} pathOptions={{ color: "#0a0a0b", weight: 4, opacity: 0.65 }} />
          {ordem.map((c, i) => (
            <Marker
              key={c.id}
              position={[c.lat, c.lng]}
              icon={pinNumerado(i + 1, corDoCliente(c), c.emRisco)}
              ref={(m) => { if (m) markerRefs.current[c.id] = m; }}
            >
              <Popup>
                <div className="pop">
                  <div className="pop-nome">{i + 1}. {c.nome}</div>
                  <div className="pop-end">
                    {c.endereco || "endereço não informado"}{c.bairro ? `, ${c.bairro}` : ""}<br />
                    {c.cidade}/{c.uf}
                  </div>
                  <div className="pop-tel">{telefoneFmt(c.telefone) || "sem telefone"}</div>
                  <div className="pop-meta">
                    <ChipFaixa c={c} />
                    {c.emRisco && <span className="chip chip-risk"><span className="dot dot-risk" />risco</span>}
                  </div>
                  <div className="pop-info">{c.faixa ? brl(c.fat) : "cliente novo"} · {motivoVisita(c)}{c.cadencia ? ` · compra a cada ${c.cadencia}d` : ""}</div>
                  <button
                    type="button"
                    className="btn btn-ghost"
                    style={{ marginTop: 8, width: "100%", justifyContent: "center" }}
                    onClick={() => remover(c)}
                    disabled={ordem.length <= 1}
                  >
                    Tirar da rota
                  </button>
                </div>
              </Popup>
            </Marker>
          ))}
          {/* Pinos cinza: quem está perto da rota de hoje mas não entrou no
              plano — um toque adiciona, sem precisar sair da tela. */}
          {vizinhosProximos.map(({ c, dist }) => (
            <Marker key={c.id} position={[c.lat, c.lng]} icon={pinFantasma()}>
              <Popup>
                <div className="pop">
                  <div className="pop-nome">{c.nome}</div>
                  <div className="pop-meta">
                    <ChipFaixa c={c} />
                    {c.emRisco && <span className="chip chip-risk"><span className="dot dot-risk" />risco</span>}
                  </div>
                  <div className="pop-info">{c.faixa ? brl(c.fat) : "cliente novo"} · a {dist.toFixed(1)} km da rota de hoje</div>
                  <button
                    type="button"
                    className="btn btn-primary"
                    style={{ marginTop: 8, width: "100%", justifyContent: "center" }}
                    onClick={() => adicionar(c)}
                  >
                    + Adicionar à rota
                  </button>
                </div>
              </Popup>
            </Marker>
          ))}
        </MapContainer>
      </div>
    </div>
  );
}

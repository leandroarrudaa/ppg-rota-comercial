import { useEffect, useMemo, useRef, useState } from "react";
import { MapContainer, TileLayer, Marker, Polyline, Popup, useMap } from "react-leaflet";
import L from "leaflet";
import { montarPlanoSemana, rotaEstrada, motivoVisita, DIAS } from "../lib/rota";
import { recomendar } from "../lib/recomendacao";
import { gerarPdfDia } from "../lib/pdf";
import { FAIXA_COR, FAIXA_CHIP, FAIXA_DOT, brl, telefoneFmt, recenciaTexto } from "../lib/format";
import MapAutoSize from "../components/MapAutoSize";

function pinNumerado(n, cor, risco) {
  return L.divIcon({
    className: "",
    html: `<div class="pin-num" style="background:${cor};${risco ? "box-shadow:0 0 0 3px #e8543f;" : ""}">${n}</div>`,
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
    map.fitBounds(
      [[Math.min(...lats), Math.min(...lngs)], [Math.max(...lats), Math.max(...lngs)]],
      { padding: [60, 60], maxZoom: 15 }
    );
  }, [pontos]);
  return null;
}

export default function VisitasView({ clientes }) {
  const [capacidade, setCapacidade] = useState(12);
  const [dia, setDia] = useState(0);
  const [estrada, setEstrada] = useState(null);
  const [carregandoRota, setCarregandoRota] = useState(false);
  const [aberto, setAberto] = useState(null);
  const mapRef = useRef(null);
  const markerRefs = useRef({});

  // centraliza no pin e abre o balão (usado ao clicar no nome da lista)
  function focar(c) {
    const map = mapRef.current;
    if (map) map.setView([c.lat, c.lng], Math.max(map.getZoom(), 14), { animate: true });
    const mk = markerRefs.current[c.id];
    if (mk) mk.openPopup();
  }

  const planos = useMemo(() => montarPlanoSemana(clientes, capacidade), [clientes, capacidade]);
  const plano = planos[dia] || planos[0];

  useEffect(() => {
    let vivo = true;
    setEstrada(null);
    if (!plano || plano.clientes.length < 2) return;
    setCarregandoRota(true);
    rotaEstrada(plano.clientes)
      .then((r) => vivo && setEstrada(r))
      .catch(() => vivo && setEstrada(null))
      .finally(() => vivo && setCarregandoRota(false));
    return () => { vivo = false; };
  }, [plano]);

  if (!plano) return <div className="vazio">Nenhum cliente ativo para visitar neste período.</div>;

  const km = estrada ? estrada.km : plano.kmReta * 1.35;
  const min = estrada ? estrada.min : (plano.kmReta * 1.35) / 0.6;
  const linha = estrada ? estrada.linha : plano.clientes.map((c) => [c.lat, c.lng]);

  return (
    <div className="mapa-layout">
      <aside className="painel">
        <div className="painel-head">
          <h3>Plano de visitas</h3>
          <p className="muted" style={{ fontSize: 13 }}>Rota presencial · valor + economia</p>
        </div>

        <div className="dias">
          {DIAS.map((d, i) => (
            <button key={d} className={"dia-btn" + (i === dia ? " on" : "")} onClick={() => setDia(i)}>
              {d.slice(0, 3)}
            </button>
          ))}
        </div>

        <div className="filtro-grupo">
          <span className="filtro-titulo">Visitas por dia: <b style={{ color: "var(--ink)" }}>{capacidade}</b></span>
          <input type="range" min="5" max="25" value={capacidade} onChange={(e) => setCapacidade(+e.target.value)} className="slider" />
        </div>

        <div className="resumo">
          <div className="resumo-item"><span>Visitas</span><b>{plano.clientes.length}</b></div>
          <div className="resumo-item"><span>Distância</span><b>{km.toFixed(0)} km {carregandoRota && <small className="faint">…</small>}</b></div>
          <div className="resumo-item"><span>Tempo em rota</span><b>{Math.floor(min / 60)}h{String(Math.round(min % 60)).padStart(2, "0")}</b></div>
          <div className="resumo-item destaque"><span>Faturamento do roteiro</span><b>{brl(plano.valor)}</b></div>
        </div>

        <button
          className="btn btn-primary"
          style={{ width: "100%", justifyContent: "center" }}
          onClick={() => gerarPdfDia({ diaNome: DIAS[dia], clientes: plano.clientes, km, min, valor: plano.valor })}
        >
          Baixar PDF da rota
        </button>

        <div className="filtro-grupo">
          <span className="filtro-titulo">Ordem de visita <span className="faint" style={{ textTransform: "none", fontWeight: 500 }}>· toque para ver a ação</span></span>
          <ol className="rota-lista">
            {plano.clientes.map((c, i) => {
              const rec = recomendar(c);
              const open = aberto === c.id;
              return (
                <li key={c.id} className={"rota-item" + (open ? " aberto" : "")} onClick={() => { setAberto(open ? null : c.id); focar(c); }}>
                  <span className="ordem-num" style={{ background: FAIXA_COR[c.faixa] }}>{i + 1}</span>
                  <div className="rota-info">
                    <div className="rota-nome">{c.nome}</div>
                    <div className="rota-meta">
                      <span className={"chip " + FAIXA_CHIP[c.faixa]}><span className={"dot " + FAIXA_DOT[c.faixa]} />{c.faixa}</span>
                      {c.emRisco && <span className="chip chip-risk"><span className="dot dot-risk" />risco</span>}
                    </div>
                    <div className="faint" style={{ fontSize: 12 }}>{c.bairro || c.cidade} · {brl(c.fat)}</div>
                    {open && (
                      <div className="rota-rec">
                        <b style={{ color: rec.cor }}>{rec.tag}</b>
                        <span>{rec.texto}</span>
                      </div>
                    )}
                  </div>
                </li>
              );
            })}
          </ol>
        </div>
      </aside>

      <div className="mapa-wrap">
        <MapContainer ref={mapRef} center={[-25.095, -50.16]} zoom={12} style={{ height: "100%", width: "100%" }}>
          <TileLayer url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png" attribution="&copy; OpenStreetMap &copy; CARTO" subdomains="abcd" />
          <MapAutoSize />
          <FitRota pontos={plano.clientes} />
          <Polyline positions={linha} pathOptions={{ color: "#0a0a0b", weight: 4, opacity: 0.65 }} />
          {plano.clientes.map((c, i) => (
            <Marker
              key={c.id}
              position={[c.lat, c.lng]}
              icon={pinNumerado(i + 1, FAIXA_COR[c.faixa], c.emRisco)}
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
                    <span className={"chip " + FAIXA_CHIP[c.faixa]}><span className={"dot " + FAIXA_DOT[c.faixa]} />{c.faixa}</span>
                    {c.emRisco && <span className="chip chip-risk"><span className="dot dot-risk" />risco</span>}
                  </div>
                  <div className="pop-info">{brl(c.fat)} · {motivoVisita(c)}{c.cadencia ? ` · compra a cada ${c.cadencia}d` : ""}</div>
                </div>
              </Popup>
            </Marker>
          ))}
        </MapContainer>
      </div>
    </div>
  );
}

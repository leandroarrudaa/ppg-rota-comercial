import { useEffect, useMemo, useState } from "react";
import { CircleMarker, MapContainer, Marker, Tooltip, useMap } from "react-leaflet";
import L from "leaflet";
import FundoMapa from "../components/FundoMapa";
import MapAutoSize from "../components/MapAutoSize";
import ChipFaixa from "../components/ChipFaixa";
import FiltroPotencial from "../components/FiltroPotencial";
import FichaCliente from "./FichaCliente";
import NovoClienteModal from "./NovoClienteModal";
import { distKm, estaNaHoraDeVisitar, textoAgenda } from "../lib/rota";
import { FAIXAS, brl, corDoCliente, num } from "../lib/format";
import { aplicarFiltroPotencial, passaFiltroPotencial, useFiltroPotencial } from "../lib/potencial";

const FXKEY = { Ouro: "gold", Prata: "silver", Bronze: "bronze" };
const NOTAS_RFM = [1, 2, 3, 4, 5];
const RFM_PADRAO = { rMin: 1, rMax: 5, fMin: 1, fMax: 5, mMin: 1, mMax: 5 };
const QUANTIDADES = [5, 10, 20, 30];

function mensagemErroGps(err) {
  if (err.code === 1) return "O celular não liberou a localização. Permita o acesso à localização pro site e toque em \"Atualizar minha posição\".";
  if (err.code === 3) return "O GPS demorou pra responder. Toque em \"Atualizar minha posição\" pra tentar de novo.";
  return "Não foi possível pegar a localização. Toque em \"Atualizar minha posição\" pra tentar de novo.";
}

function semAcento(texto) {
  return String(texto || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

function distanciaTexto(km) {
  if (km < 1) return `${Math.round(km * 1000 / 10) * 10} m`;
  return `${km.toLocaleString("pt-BR", { maximumFractionDigits: 1 })} km`;
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

// Enquadra a posição do vendedor junto com as empresas listadas — refaz só
// quando muda quem está na lista ou a posição, não a cada render.
function Enquadrar({ posicao, pontos }) {
  const map = useMap();
  const chave = `${posicao?.lat},${posicao?.lng}|${pontos.map((p) => p.id).join(",")}`;
  useEffect(() => {
    if (!posicao) return;
    function enquadrar() {
      const { width, height } = map.getContainer().getBoundingClientRect();
      if (!width || !height) return false;
      map.invalidateSize();
      const lats = [posicao.lat, ...pontos.map((p) => p.lat)];
      const lngs = [posicao.lng, ...pontos.map((p) => p.lng)];
      if (lats.length === 1) {
        map.setView([posicao.lat, posicao.lng], 15);
      } else {
        map.fitBounds(
          [[Math.min(...lats), Math.min(...lngs)], [Math.max(...lats), Math.max(...lngs)]],
          { padding: [50, 50], maxZoom: 16 },
        );
      }
      return true;
    }
    if (enquadrar()) return;
    // No celular o mapa começa escondido (lista aberta): enquadrar com o
    // container 0x0 deixa o mapa cinza e fora do lugar — espera ele aparecer.
    const ro = new ResizeObserver(() => { if (enquadrar()) ro.disconnect(); });
    ro.observe(map.getContainer());
    return () => ro.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chave]);
  return null;
}

// "Perto de mim": a partir de onde o vendedor está agora (GPS do celular),
// as N empresas mais próximas que passam nos mesmos filtros da Rota do Dia.
// Pensada pro meio do dia — está numa visita ou entrega e quer aproveitar o
// que tem em volta. Usa a carteira já carregada no app: nada de ir ao servidor.
export default function PertoDeMimView({
  clientes, aoAtualizarCliente, visitaPendente, aoIniciarVisita, aoFinalizarVisita, aoCancelarVisita,
  visitasHojeIds, usuario,
}) {
  const [posicao, setPosicao] = useState(null); // { lat, lng, origem: "gps" | "visita", nome? }
  const [localizando, setLocalizando] = useState(false);
  const [avisoGps, setAvisoGps] = useState("");

  const [quantidade, setQuantidade] = useState(10);
  const [buscaTexto, setBuscaTexto] = useState("");
  const [incluirVisitados, setIncluirVisitados] = useState(false);

  const [faixasOn, setFaixasOn] = useState({ Ouro: true, Prata: true, Bronze: true });
  const [soRisco, setSoRisco] = useState(false);
  const [fp, mudarFp] = useFiltroPotencial();
  const [faturamentoMin, setFaturamentoMin] = useState(0);
  const [rfm, setRfm] = useState(RFM_PADRAO);
  const [filtrosAbertos, setFiltrosAbertos] = useState(false);

  const [fichaAberta, setFichaAberta] = useState(null);
  const [novoClienteAberto, setNovoClienteAberto] = useState(false);
  // Diferente da Rota do Dia, a lista aqui não depende da área visível do
  // mapa — então no celular abre direto na lista, que é o que ele vai usar.
  const [modoMobile, setModoMobile] = useState("painel");

  function localizar() {
    if (!navigator.geolocation) {
      setAvisoGps("Este aparelho não informa a localização.");
      return;
    }
    setLocalizando(true);
    setAvisoGps("");
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setPosicao({ lat: pos.coords.latitude, lng: pos.coords.longitude, origem: "gps" });
        setLocalizando(false);
      },
      (err) => {
        setLocalizando(false);
        setAvisoGps(mensagemErroGps(err));
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 30000 },
    );
  }

  useEffect(() => { localizar(); }, []);

  // Se o GPS falhar no meio de uma visita, a própria empresa visitada serve
  // de ponto de partida — é justamente o caso de uso desta tela.
  const clienteDaVisita = visitaPendente?.clienteId
    ? clientes.find((c) => c.id === visitaPendente.clienteId && c.lat != null)
    : null;

  function usarEmpresaDaVisita() {
    setPosicao({ lat: clienteDaVisita.lat, lng: clienteDaVisita.lng, origem: "visita", nome: clienteDaVisita.nome });
    setAvisoGps("");
  }

  const rfmPadrao = Object.keys(RFM_PADRAO).every((k) => rfm[k] === RFM_PADRAO[k]);

  function passaFiltro(c) {
    if (c.origem === "antigo" && c.faixa && !faixasOn[c.faixa]) return false;
    if (c.origem === "antigo" && faturamentoMin > 0 && (c.fat || 0) < faturamentoMin) return false;
    if (c.origem === "antigo" && !rfmPadrao) {
      if (c.R == null || c.R < rfm.rMin || c.R > rfm.rMax) return false;
      if (c.F == null || c.F < rfm.fMin || c.F > rfm.fMax) return false;
      if (c.M == null || c.M < rfm.mMin || c.M > rfm.mMax) return false;
    }
    if (soRisco && !c.emRisco) return false;
    if (!passaFiltroPotencial(c, fp)) return false;
    return true;
  }

  // Quem pode aparecer: tem pino de verdade (localização aproximada no centro
  // da cidade daria distância errada), aceita visita presencial e está ativo.
  const visitaveis = useMemo(
    () => clientes.filter((c) => c.lat != null && c.lng != null && c.geo !== "cidade" && c.aceitaVisita !== false && c.status !== "inativo"),
    [clientes],
  );

  // Já visitado = foi hoje, ou foi antes e ainda não chegou a data de voltar
  // (mesma regra do Plano da Semana).
  const jaVisitado = (c) => visitasHojeIds?.has(c.id) || !estaNaHoraDeVisitar(c);

  const { lista, escondidosVisitados } = useMemo(() => {
    const termo = semAcento(buscaTexto.trim());
    const termoDigitos = buscaTexto.replace(/\D/g, "");
    let base = visitaveis.filter(passaFiltro);
    if (termo.length >= 2) {
      base = base.filter((c) =>
        semAcento(c.nome).includes(termo)
        || (c.codigoErp && String(c.codigoErp).includes(buscaTexto.trim()))
        || (termoDigitos.length >= 3 && (c.cnpj || "").replace(/\D/g, "").includes(termoDigitos)));
    }
    const escondidos = incluirVisitados ? 0 : base.filter(jaVisitado).length;
    if (!incluirVisitados) base = base.filter((c) => !jaVisitado(c));
    base = aplicarFiltroPotencial(base, fp);
    if (!posicao) return { lista: [], escondidosVisitados: escondidos };
    const comDistancia = base
      .map((c) => ({ ...c, distancia: distKm(posicao, c) }))
      .sort((a, b) => a.distancia - b.distancia)
      .slice(0, quantidade);
    return { lista: comDistancia, escondidosVisitados: escondidos };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visitaveis, posicao, quantidade, buscaTexto, incluirVisitados, faixasOn, soRisco, faturamentoMin, rfm, rfmPadrao, fp, visitasHojeIds]);

  function abrirFicha(c) {
    setFichaAberta(c);
  }
  function atualizarFicha(atualizado) {
    setFichaAberta(atualizado);
    aoAtualizarCliente(atualizado);
  }
  function aoCriarCliente(novo) {
    aoAtualizarCliente(novo);
    setFichaAberta(novo);
  }

  function linkRotaGoogle(c) {
    return `https://www.google.com/maps/dir/?api=1&destination=${c.lat},${c.lng}&travelmode=driving`;
  }

  const contagemFaixa = (f) => lista.filter((c) => c.faixa === f).length;

  return (
    <div className={"mapa-layout rota-dia-layout" + (modoMobile === "mapa" ? " modo-mapa-mobile" : " modo-painel-mobile")}>
      <button
        type="button"
        className="btn-alternar-mobile"
        onClick={() => setModoMobile((m) => (m === "mapa" ? "painel" : "mapa"))}
      >
        {modoMobile === "mapa" ? "☰ Ver lista" : "🗺️ Ver mapa"}
      </button>
      <button type="button" className="btn-achei-flutuante" onClick={() => setNovoClienteAberto(true)}>
        + Achei uma empresa
      </button>

      <aside className="painel rota-dia-painel">
        <div className="painel-head">
          <h3>Perto de mim</h3>
          <p className="muted" style={{ fontSize: 13 }}>
            {posicao
              ? posicao.origem === "visita"
                ? `A partir de ${posicao.nome} (visita em andamento).`
                : "As empresas mais perto de onde você está agora."
              : localizando ? "Pegando sua localização…" : "Precisamos da sua localização pra mostrar quem está perto."}
          </p>
        </div>

        <button type="button" className="btn-achei-empresa" onClick={() => setNovoClienteAberto(true)}>
          + Achei uma empresa
        </button>

        <button className="btn btn-ghost" style={{ width: "100%", justifyContent: "center" }} disabled={localizando} onClick={localizar}>
          {localizando ? "Localizando…" : "📍 Atualizar minha posição"}
        </button>
        {avisoGps && <p className="login-erro" style={{ fontSize: 13 }}>{avisoGps}</p>}
        {clienteDaVisita && posicao?.origem !== "visita" && (avisoGps || !posicao) && (
          <button type="button" className="btn btn-ghost" style={{ width: "100%", justifyContent: "center" }} onClick={usarEmpresaDaVisita}>
            Usar a empresa da visita atual ({clienteDaVisita.nome})
          </button>
        )}

        <div className="filtro-grupo">
          <span className="filtro-titulo">Quantas empresas mostrar</span>
          <div className="periodo-btns">
            {QUANTIDADES.map((q) => (
              <button
                key={q}
                type="button"
                className={"dia-btn" + (quantidade === q ? " on" : "")}
                onClick={() => setQuantidade(q)}
              >
                {q}
              </button>
            ))}
          </div>
        </div>

        <div className="field search">
          <svg className="search-ico" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
            <circle cx="11" cy="11" r="7" /><line x1="21" y1="21" x2="16.7" y2="16.7" />
          </svg>
          <input
            className="input input-search"
            placeholder="Buscar por nome, código ou CNPJ…"
            value={buscaTexto}
            onChange={(e) => setBuscaTexto(e.target.value)}
          />
        </div>

        <label className="ficha-radio" style={{ fontSize: 13 }}>
          <input type="checkbox" checked={incluirVisitados} onChange={(e) => setIncluirVisitados(e.target.checked)} />
          Mostrar também os já visitados
          {!incluirVisitados && escondidosVisitados > 0 && (
            <span className="faint">&nbsp;({escondidosVisitados} {escondidosVisitados === 1 ? "escondido" : "escondidos"})</span>
          )}
        </label>

        <button
          type="button"
          className="btn-toggle-filtros"
          onClick={() => setFiltrosAbertos((v) => !v)}
        >
          {filtrosAbertos ? "▲ Menos filtros" : "▾ Mais filtros (faturamento, faixa, RFM, risco)"}
        </button>

        <div className={"rota-dia-filtros-extra" + (filtrosAbertos ? " aberto" : "")}>
          <FiltroPotencial filtro={fp} aoMudar={mudarFp} />

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
                        <span className="medal-count">{num(contagemFaixa(f))}</span>
                      </span>
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          <div className="filtro-grupo">
            <span className="filtro-titulo">
              Matriz RFM{" "}
              <span className="faint" style={{ textTransform: "none", fontWeight: 500 }}>
                · R recência, F frequência, M valor (1 a 5)
              </span>
            </span>
            <div className="rfm-linhas">
              {[["Recência (R)", "rMin", "rMax"], ["Frequência (F)", "fMin", "fMax"], ["Valor (M)", "mMin", "mMax"]].map(([rotulo, kMin, kMax]) => (
                <div key={kMin} className="rfm-linha">
                  <span className="rfm-label">{rotulo}</span>
                  <select className="input rfm-select" value={rfm[kMin]} onChange={(e) => setRfm((s) => ({ ...s, [kMin]: +e.target.value }))}>
                    {NOTAS_RFM.map((n) => <option key={n} value={n}>{n}</option>)}
                  </select>
                  <span className="faint">até</span>
                  <select className="input rfm-select" value={rfm[kMax]} onChange={(e) => setRfm((s) => ({ ...s, [kMax]: +e.target.value }))}>
                    {NOTAS_RFM.map((n) => <option key={n} value={n}>{n}</option>)}
                  </select>
                </div>
              ))}
            </div>
            <button
              type="button"
              className="btn btn-ghost"
              style={{ fontSize: 12, padding: "0.4rem 0.7rem" }}
              onClick={() => setRfm({ rMin: 1, rMax: 2, fMin: 1, fMax: 2, mMin: 4, mMax: 5 })}
              title="R até 2 (sumiu) · F até 2 (compra raro) · M de 4 a 5 (quando compra, compra bem)"
            >
              Potencial esquecido: comprou bem, sumiu, é raro
            </button>
            {!rfmPadrao && (
              <button type="button" className="btn btn-ghost" style={{ fontSize: 12, padding: "0.4rem 0.7rem" }} onClick={() => setRfm(RFM_PADRAO)}>
                Limpar matriz RFM
              </button>
            )}
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

        <div className="filtro-grupo">
          <span className="filtro-titulo">Mais perto {posicao ? `(${lista.length})` : ""}</span>
          {!posicao ? (
            <p className="muted" style={{ fontSize: 13 }}>{localizando ? "Pegando sua localização…" : "Sem localização ainda."}</p>
          ) : lista.length === 0 ? (
            <p className="muted" style={{ fontSize: 13 }}>Nenhuma empresa passa nesses filtros.</p>
          ) : (
            <ol className="rota-lista">
              {lista.map((c, i) => {
                const emAndamento = visitaPendente?.clienteId === c.id;
                return (
                  <li key={c.id} className={jaVisitado(c) ? "rota-item-visitado-leve" : ""} onClick={() => abrirFicha(c)}>
                    <span className="ordem-num" style={{ background: corDoCliente(c) }}>{i + 1}</span>
                    <div className="rota-info" style={{ flex: 1 }}>
                      <div className="rota-nome">
                        {c.nome} {c.temPromessaPendente && <span title="Tem promessa pendente">🎁</span>}
                      </div>
                      <div className="faint" style={{ fontSize: 12 }}>
                        {c.codigoErp ? `código ${c.codigoErp} · ` : ""}{c.bairro || c.cidade || "sem bairro"}
                      </div>
                      <div className="rota-meta">
                        <ChipFaixa c={c} />
                        <span className="faint">{c.faixa ? brl(c.fat) : "cliente novo"}</span>
                      </div>
                      <div className="faint" style={{ fontSize: 12 }}>
                        {emAndamento ? "visita em andamento" : textoAgenda(c)}
                      </div>
                    </div>
                    <div className="perto-acoes">
                      <b className="perto-dist">{distanciaTexto(c.distancia)}</b>
                      <a
                        className="btn btn-ghost perto-ir"
                        href={linkRotaGoogle(c)}
                        target="_blank"
                        rel="noopener noreferrer"
                        onClick={(e) => e.stopPropagation()}
                      >
                        Ir até lá
                      </a>
                    </div>
                  </li>
                );
              })}
            </ol>
          )}
        </div>
      </aside>

      <div className="mapa-wrap">
        <MapContainer
          center={posicao ? [posicao.lat, posicao.lng] : [-25.095, -50.16]}
          zoom={14}
          style={{ height: "100%", width: "100%" }}
        >
          <FundoMapa />
          <MapAutoSize />
          <Enquadrar posicao={posicao} pontos={lista} />
          {posicao && (
            <CircleMarker
              center={[posicao.lat, posicao.lng]}
              radius={9}
              pathOptions={{ color: "#fff", weight: 3, fillColor: "#1a73e8", fillOpacity: 1 }}
            >
              {/* não-permanente: fixa, cobria justamente os pinos mais perto */}
              <Tooltip direction="top" offset={[0, -10]}>Você está aqui</Tooltip>
            </CircleMarker>
          )}
          {lista.map((c, i) => (
            <Marker
              key={c.id}
              position={[c.lat, c.lng]}
              icon={pinNumerado(i + 1, corDoCliente(c), c.emRisco)}
              eventHandlers={{ click: () => abrirFicha(c) }}
            >
              <Tooltip>
                <b>{i + 1}. {c.nome}</b><br />
                {distanciaTexto(c.distancia)} · {c.faixa ? `${c.faixa} · ${brl(c.fat)}` : "Cliente novo"}
              </Tooltip>
            </Marker>
          ))}
        </MapContainer>
      </div>

      {fichaAberta && (
        <FichaCliente
          cliente={fichaAberta}
          aoFechar={() => setFichaAberta(null)}
          aoAtualizar={atualizarFicha}
          visitaPendente={visitaPendente}
          aoIniciarVisita={aoIniciarVisita}
          aoFinalizarVisita={aoFinalizarVisita}
          aoCancelarVisita={aoCancelarVisita}
          usuario={usuario}
        />
      )}
      {novoClienteAberto && (
        <NovoClienteModal
          gpsAoAbrir
          aoFechar={() => setNovoClienteAberto(false)}
          aoCriado={aoCriarCliente}
        />
      )}
    </div>
  );
}

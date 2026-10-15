import { useEffect, useState } from "react";
import { MapContainer, Marker, useMap, useMapEvents } from "react-leaflet";
import FundoMapa from "../components/FundoMapa";
import { api } from "../lib/api";

// Marca o pin onde o usuário clicar no mini-mapa — sem geocodificação:
// decisão explícita (mais simples, sem dependência externa, mais preciso
// que tentar geocodificar um endereço digitado).
function CapturarClique({ pin, aoClicar }) {
  useMapEvents({ click: (e) => aoClicar([e.latlng.lat, e.latlng.lng]) });
  return pin ? <Marker position={pin} /> : null;
}

// Leva o mini-mapa até o ponto vindo do GPS (o clique manual não precisa:
// o usuário já está olhando pra onde tocou).
function IrPara({ alvo }) {
  const map = useMap();
  useEffect(() => {
    if (alvo) map.setView(alvo, 17);
  }, [alvo, map]);
  return null;
}

// Traduz o erro do navegador pra uma mensagem que o vendedor entenda.
function mensagemErroGps(err) {
  if (err.code === 1) return "O celular não liberou a localização. Permita o acesso à localização pro site, ou toque no mapa onde fica a empresa.";
  if (err.code === 3) return "O GPS demorou pra responder. Tente de novo ou toque no mapa onde fica a empresa.";
  return "Não foi possível pegar a localização. Toque no mapa onde fica a empresa.";
}

export default function NovoClienteModal({ aoFechar, aoCriado, centro, gpsAoAbrir = false }) {
  const [pin, setPin] = useState(null);
  const [alvoGps, setAlvoGps] = useState(null);
  const [localizando, setLocalizando] = useState(false);
  const [avisoGps, setAvisoGps] = useState("");
  const [nome, setNome] = useState("");
  const [endereco, setEndereco] = useState("");
  const [bairro, setBairro] = useState("");
  const [cidade, setCidade] = useState("");
  const [uf, setUf] = useState("");
  const [cnpj, setCnpj] = useState("");
  const [contatoNome, setContatoNome] = useState("");
  const [contatoCelular, setContatoCelular] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState("");

  // "Estou aqui": usa a posição do celular como pin — em campo o vendedor
  // está parado na frente da empresa, então é mais preciso que tocar no mapa.
  function usarMinhaLocalizacao() {
    if (!navigator.geolocation) {
      setAvisoGps("Este aparelho não informa a localização. Toque no mapa onde fica a empresa.");
      return;
    }
    setLocalizando(true);
    setAvisoGps("");
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const ponto = [pos.coords.latitude, pos.coords.longitude];
        setPin(ponto);
        setAlvoGps(ponto);
        setLocalizando(false);
        const precisao = Math.round(pos.coords.accuracy);
        setAvisoGps(precisao > 50
          ? `Localização aproximada (cerca de ${precisao} m). Se o pin não estiver na empresa, toque no lugar certo.`
          : "");
      },
      (err) => {
        setLocalizando(false);
        setAvisoGps(mensagemErroGps(err));
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 },
    );
  }

  useEffect(() => {
    if (gpsAoAbrir) usarMinhaLocalizacao();
  }, [gpsAoAbrir]); // eslint-disable-line react-hooks/exhaustive-deps

  async function salvar(e) {
    e.preventDefault();
    if (!pin) { setErro("Marque no mapa onde fica a empresa."); return; }
    if (!nome.trim()) { setErro("Informe o nome da empresa."); return; }
    setSalvando(true);
    setErro("");
    try {
      const novo = await api.post("/api/clientes/manual", {
        nome: nome.trim(),
        lat: pin[0],
        lng: pin[1],
        endereco: endereco.trim() || null,
        bairro: bairro.trim() || null,
        cidade: cidade.trim() || null,
        uf: uf.trim() || null,
        cnpj: cnpj.trim() || null,
        contatoNome: contatoNome.trim() || null,
        contatoCelular: contatoCelular.trim() || null,
      });
      aoCriado(novo);
      aoFechar();
    } catch (err) {
      setErro(err.message);
    } finally {
      setSalvando(false);
    }
  }

  return (
    <div className="modal-fundo" onClick={aoFechar}>
      <div className="modal-ficha" onClick={(e) => e.stopPropagation()}>
        <button className="modal-fechar" onClick={aoFechar} aria-label="Fechar">×</button>

        <div className="ficha-header">
          <h2>Cadastrar cliente novo</h2>
          <p className="muted" style={{ fontSize: 13 }}>
            Se estiver na frente da empresa, use “Estou aqui”. Senão, toque no mapa onde ela fica.
          </p>
        </div>

        <button
          type="button"
          className="btn btn-ghost"
          style={{ width: "100%", justifyContent: "center", marginTop: 10 }}
          onClick={usarMinhaLocalizacao}
          disabled={localizando}
        >
          {localizando ? "Buscando sua localização…" : "📍 Estou aqui (usar minha localização)"}
        </button>

        <div className="novo-cliente-mapa">
          <MapContainer center={centro || [-25.095, -50.16]} zoom={13} style={{ height: "100%", width: "100%" }}>
            <FundoMapa />
            <CapturarClique pin={pin} aoClicar={setPin} />
            <IrPara alvo={alvoGps} />
          </MapContainer>
        </div>
        {avisoGps && <p className="muted" style={{ fontSize: 12, marginTop: 4 }}>{avisoGps}</p>}
        {!pin && !localizando && <p className="muted" style={{ fontSize: 12, marginTop: 4 }}>Nenhum ponto marcado ainda.</p>}

        <form onSubmit={salvar}>
          <div className="ficha-secao" style={{ borderTop: "none", paddingTop: 8 }}>
            <span className="filtro-titulo">Nome da empresa *</span>
            <input className="input" value={nome} onChange={(e) => setNome(e.target.value)} autoFocus />
          </div>

          <div className="ficha-secao">
            <span className="filtro-titulo">Endereço</span>
            <input className="input" placeholder="Endereço (texto livre)" value={endereco} onChange={(e) => setEndereco(e.target.value)} />
            <div className="ficha-contato" style={{ marginTop: 6 }}>
              <input className="input" placeholder="Bairro" value={bairro} onChange={(e) => setBairro(e.target.value)} />
              <input className="input" placeholder="Cidade" value={cidade} onChange={(e) => setCidade(e.target.value)} />
              <input className="input" placeholder="UF" maxLength={2} style={{ maxWidth: 70 }} value={uf} onChange={(e) => setUf(e.target.value.toUpperCase())} />
            </div>
          </div>

          <div className="ficha-secao">
            <span className="filtro-titulo">Contato (opcional)</span>
            <div className="ficha-contato">
              <input className="input" placeholder="CNPJ" value={cnpj} onChange={(e) => setCnpj(e.target.value)} />
              <input className="input" placeholder="Nome do contato" value={contatoNome} onChange={(e) => setContatoNome(e.target.value)} />
              <input className="input" placeholder="Celular" value={contatoCelular} onChange={(e) => setContatoCelular(e.target.value)} />
            </div>
          </div>

          {erro && <div className="login-erro" style={{ marginTop: 12 }}>{erro}</div>}

          <button className="btn btn-primary" type="submit" disabled={salvando} style={{ width: "100%", justifyContent: "center", marginTop: 16 }}>
            {salvando ? "Salvando…" : "Cadastrar e abrir a ficha"}
          </button>
        </form>
      </div>
    </div>
  );
}

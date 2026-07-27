import { useState } from "react";
import { MapContainer, TileLayer, Marker, useMapEvents } from "react-leaflet";
import { api } from "../lib/api";

// Marca o pin onde o usuário clicar no mini-mapa — sem geocodificação:
// decisão explícita (mais simples, sem dependência externa, mais preciso
// que tentar geocodificar um endereço digitado).
function CapturarClique({ pin, aoClicar }) {
  useMapEvents({ click: (e) => aoClicar([e.latlng.lat, e.latlng.lng]) });
  return pin ? <Marker position={pin} /> : null;
}

export default function NovoClienteModal({ aoFechar, aoCriado, centro }) {
  const [pin, setPin] = useState(null);
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
            Clique no mapa pra marcar onde fica a empresa.
          </p>
        </div>

        <div className="novo-cliente-mapa">
          <MapContainer center={centro || [-25.095, -50.16]} zoom={13} style={{ height: "100%", width: "100%" }}>
            <TileLayer url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png" attribution="&copy; OpenStreetMap &copy; CARTO" subdomains="abcd" />
            <CapturarClique pin={pin} aoClicar={setPin} />
          </MapContainer>
        </div>
        {!pin && <p className="muted" style={{ fontSize: 12, marginTop: 4 }}>Nenhum ponto marcado ainda.</p>}

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
            {salvando ? "Salvando…" : "Cadastrar cliente"}
          </button>
        </form>
      </div>
    </div>
  );
}

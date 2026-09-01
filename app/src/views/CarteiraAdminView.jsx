import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api";
import { FAIXA_CHIP, FAIXA_DOT, brl } from "../lib/format";

const TAMANHO_PAGINA = 50;

const FILTROS_INICIAIS = {
  busca: "",
  faixa: "",
  cidade: "",
  origem: "",
  status: "ativo",
  semLocalizacao: false,
  vinculo: "",
  ordenar: "faturamento",
};

// Lista completa da carteira para o gerente: busca, filtros, vínculo manual e
// inativação em lote. Diferente do Mapa e da Rota do Dia, aqui NADA fica
// escondido por padrão — inativo e cliente sem coordenada aparecem, porque é
// exatamente o que se vem consertar nesta tela.
export default function CarteiraAdminView() {
  const [filtros, setFiltros] = useState(FILTROS_INICIAIS);
  const [pagina, setPagina] = useState(1);
  const [dados, setDados] = useState(null);
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState("");
  const [cidades, setCidades] = useState([]);
  const [selecionados, setSelecionados] = useState(new Set());
  const [ocupado, setOcupado] = useState("");
  const [aviso, setAviso] = useState("");

  useEffect(() => {
    api.get("/api/clientes/cidades").then(setCidades).catch(() => setCidades([]));
  }, []);

  const carregar = useCallback(() => {
    setCarregando(true);
    setErro("");
    const params = new URLSearchParams({
      pagina: String(pagina),
      tamanho: String(TAMANHO_PAGINA),
      status: filtros.status,
      ordenar: filtros.ordenar,
    });
    if (filtros.busca.trim().length >= 2) params.set("busca", filtros.busca.trim());
    if (filtros.faixa) params.set("faixa", filtros.faixa);
    if (filtros.cidade) params.set("cidade", filtros.cidade);
    if (filtros.origem) params.set("origem", filtros.origem);
    if (filtros.vinculo) params.set("vinculo", filtros.vinculo);
    if (filtros.semLocalizacao) params.set("semLocalizacao", "true");

    api.get(`/api/clientes/admin?${params}`)
      .then(setDados)
      .catch((e) => { setDados(null); setErro(e.message); })
      .finally(() => setCarregando(false));
  }, [filtros, pagina]);

  // Espera parar de digitar antes de consultar: cada busca é uma ida ao banco,
  // que fica longe do servidor.
  useEffect(() => {
    const t = setTimeout(carregar, 300);
    return () => clearTimeout(t);
  }, [carregar]);

  function mudarFiltro(campo, valor) {
    setFiltros((f) => ({ ...f, [campo]: valor }));
    setPagina(1);
    setSelecionados(new Set());
  }

  function alternar(id) {
    setSelecionados((s) => {
      const novo = new Set(s);
      if (novo.has(id)) novo.delete(id);
      else novo.add(id);
      return novo;
    });
  }

  function alternarTodos() {
    const ids = (dados?.itens || []).map((c) => c.id);
    setSelecionados((s) => (ids.every((id) => s.has(id)) ? new Set() : new Set(ids)));
  }

  async function alterarStatus(status) {
    setOcupado(status);
    setAviso("");
    try {
      const r = await api.patch("/api/clientes/lote/status", {
        clienteIds: [...selecionados],
        status,
      });
      setAviso(
        `${r.alterados} ${r.alterados === 1 ? "cliente" : "clientes"} ` +
        `${status === "inativo" ? "inativado(s)" : "reativado(s)"}.`
      );
      setSelecionados(new Set());
      carregar();
    } catch (e) {
      setErro(e.message);
    } finally {
      setOcupado("");
    }
  }

  async function vincularSelecionados() {
    if (selecionados.size < 2) return;
    setOcupado("vincular");
    setAviso("");
    try {
      const r = await api.post("/api/vinculos", { clienteIds: [...selecionados] });
      setAviso(`Vinculados como "${r.nomePreferido}" — ${r.membros.length} CNPJs no mesmo cliente.`);
      setSelecionados(new Set());
      carregar();
    } catch (e) {
      setErro(e.message);
    } finally {
      setOcupado("");
    }
  }

  const total = dados?.total || 0;
  const paginas = Math.max(1, Math.ceil(total / TAMANHO_PAGINA));
  const itens = dados?.itens || [];
  const todosMarcados = itens.length > 0 && itens.every((c) => selecionados.has(c.id));

  return (
    <div className="carteira-admin">
      <div className="carteira-filtros">
        <input
          className="input"
          placeholder="Buscar por nome, CNPJ ou cidade…"
          value={filtros.busca}
          onChange={(e) => mudarFiltro("busca", e.target.value)}
        />

        <select className="input" value={filtros.status} onChange={(e) => mudarFiltro("status", e.target.value)}>
          <option value="ativo">Ativos</option>
          <option value="inativo">Inativos</option>
          <option value="todos">Todos</option>
        </select>

        <select className="input" value={filtros.faixa} onChange={(e) => mudarFiltro("faixa", e.target.value)}>
          <option value="">Todas as faixas</option>
          <option value="Ouro">Ouro</option>
          <option value="Prata">Prata</option>
          <option value="Bronze">Bronze</option>
        </select>

        <select className="input" value={filtros.cidade} onChange={(e) => mudarFiltro("cidade", e.target.value)}>
          <option value="">Todas as cidades</option>
          {cidades.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>

        <select className="input" value={filtros.origem} onChange={(e) => mudarFiltro("origem", e.target.value)}>
          <option value="">Antigos e novos</option>
          <option value="antigo">Só da carteira antiga</option>
          <option value="novo">Só cadastrados em campo</option>
        </select>

        <select className="input" value={filtros.vinculo} onChange={(e) => mudarFiltro("vinculo", e.target.value)}>
          <option value="">Com ou sem vínculo</option>
          <option value="com">Só vinculados</option>
          <option value="sem">Só não vinculados</option>
        </select>

        <select className="input" value={filtros.ordenar} onChange={(e) => mudarFiltro("ordenar", e.target.value)}>
          <option value="faturamento">Maior faturamento</option>
          <option value="nome">Nome (A-Z)</option>
          <option value="recencia">Comprou mais recente</option>
          <option value="atualizacao">Alterado por último</option>
        </select>

        <label className="carteira-check">
          <input
            type="checkbox"
            checked={filtros.semLocalizacao}
            onChange={(e) => mudarFiltro("semLocalizacao", e.target.checked)}
          />
          Só sem localização no mapa
        </label>

        <button className="btn btn-ghost" onClick={() => { setFiltros(FILTROS_INICIAIS); setPagina(1); }}>
          Limpar filtros
        </button>
      </div>

      {erro && <div className="login-erro">{erro}</div>}
      {aviso && <div className="carteira-aviso">{aviso}</div>}

      <div className="carteira-barra">
        <span className="muted" style={{ fontSize: 13 }}>
          {carregando ? "Carregando…" : `${total.toLocaleString("pt-BR")} ${total === 1 ? "cliente" : "clientes"}`}
          {filtros.semLocalizacao && !carregando && " sem localização — precisam de um pino no mapa"}
        </span>

        {selecionados.size > 0 && (
          <div className="carteira-acoes">
            <span className="muted" style={{ fontSize: 13 }}>{selecionados.size} selecionado(s)</span>
            <button
              className="btn btn-ghost"
              disabled={selecionados.size < 2 || Boolean(ocupado)}
              onClick={vincularSelecionados}
              title={selecionados.size < 2 ? "Selecione pelo menos dois CNPJs da mesma empresa" : undefined}
            >
              {ocupado === "vincular" ? "Vinculando…" : "Vincular como mesma empresa"}
            </button>
            {filtros.status === "inativo" ? (
              <button className="btn btn-primary" disabled={Boolean(ocupado)} onClick={() => alterarStatus("ativo")}>
                {ocupado === "ativo" ? "Reativando…" : "Reativar"}
              </button>
            ) : (
              <button className="btn btn-ghost" disabled={Boolean(ocupado)} onClick={() => alterarStatus("inativo")}>
                {ocupado === "inativo" ? "Inativando…" : "Inativar"}
              </button>
            )}
          </div>
        )}
      </div>

      <div className="carteira-tabela-wrap">
        <table className="carteira-tabela">
          <thead>
            <tr>
              <th style={{ width: 34 }}>
                <input type="checkbox" checked={todosMarcados} onChange={alternarTodos} aria-label="Selecionar todos" />
              </th>
              <th>Cliente</th>
              <th>Cidade</th>
              <th className="num">Faturamento</th>
              <th>Situação</th>
            </tr>
          </thead>
          <tbody>
            {itens.length === 0 && !carregando ? (
              <tr><td colSpan={5} className="muted" style={{ padding: 20, textAlign: "center" }}>
                Nenhum cliente com esses filtros.
              </td></tr>
            ) : itens.map((c) => (
              <tr key={c.id} className={selecionados.has(c.id) ? "marcada" : ""}>
                <td>
                  <input type="checkbox" checked={selecionados.has(c.id)} onChange={() => alternar(c.id)} />
                </td>
                <td>
                  <div className="carteira-nome">{c.nome}</div>
                  <div className="faint" style={{ fontSize: 12 }}>{c.cnpj || "sem CNPJ"}</div>
                </td>
                <td>{c.cidade || "—"}</td>
                <td className="num">{c.faixa ? brl(c.fat) : "—"}</td>
                <td>
                  <div className="carteira-chips">
                    {c.faixa && (
                      <span className={"chip " + FAIXA_CHIP[c.faixa]}>
                        <span className={"dot " + FAIXA_DOT[c.faixa]} />{c.faixa}
                      </span>
                    )}
                    {c.status === "inativo" && <span className="chip chip-inativo">Inativo</span>}
                    {c.origem === "novo" && <span className="chip chip-motivo">Novo</span>}
                    {!c.aceitaVisita && c.status !== "inativo" && (
                      <span className="chip chip-motivo">{c.motivoRecusaVisita === "calote" ? "Calote" : "Sem visita"}</span>
                    )}
                    {c.clienteMestreId && <span className="chip chip-motivo">Vinculado</span>}
                    {(c.lat == null || c.lng == null) && <span className="chip chip-risk">Sem local</span>}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {paginas > 1 && (
        <div className="carteira-paginacao">
          <button className="btn btn-ghost" disabled={pagina <= 1} onClick={() => setPagina((p) => p - 1)}>
            ← Anterior
          </button>
          <span className="muted" style={{ fontSize: 13 }}>Página {pagina} de {paginas}</span>
          <button className="btn btn-ghost" disabled={pagina >= paginas} onClick={() => setPagina((p) => p + 1)}>
            Próxima →
          </button>
        </div>
      )}
    </div>
  );
}

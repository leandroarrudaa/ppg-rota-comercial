import { useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";
import { FAIXA_CHIP, FAIXA_DOT, brl, num, recenciaTexto, telefoneFmt } from "../lib/format";

const TAMANHO_PAGINA = 20;

// Colunas do histórico de item — cada uma sabe extrair o valor comparável
// e se é ordenada crescente por padrão (texto/data) ou decrescente (número).
const COLUNAS_HISTORICO = [
  { campo: "descricaoProduto", rotulo: "Produto", tipo: "texto", ascPadrao: true },
  { campo: "quantidadeTotal", rotulo: "Qtd", tipo: "numero", ascPadrao: false },
  { campo: "numeroCompras", rotulo: "Compras", tipo: "numero", ascPadrao: false },
  { campo: "ultimaCompra", rotulo: "Última", tipo: "data", ascPadrao: false },
  { campo: "valorTotal", rotulo: "Valor", tipo: "numero", ascPadrao: false },
];

// Modal de ficha do cliente: dados cadastrais, contato editável, status/aceitaVisita,
// promessas pendentes, botão de iniciar visita e histórico de compra por item
// (maior valor primeiro), paginado sob demanda.
export default function FichaCliente({ cliente, aoFechar, aoAtualizar, visitaPendente, aoIniciarVisita, aoFinalizarVisita, usuario }) {
  const ehAdmin = usuario?.papel === "admin";
  const [contatoNome, setContatoNome] = useState(cliente.contatoNome || "");
  const [contatoCelular, setContatoCelular] = useState(cliente.contatoCelular || "");
  const [salvandoContato, setSalvandoContato] = useState(false);
  const [erroContato, setErroContato] = useState("");
  const [copiado, setCopiado] = useState(false);

  const [status, setStatus] = useState(cliente.status);
  const [aceitaVisita, setAceitaVisita] = useState(cliente.aceitaVisita);
  const [motivo, setMotivo] = useState(cliente.motivoRecusaVisita || "calote");
  const [salvandoStatus, setSalvandoStatus] = useState(false);
  const [erroStatus, setErroStatus] = useState("");

  const [promessas, setPromessas] = useState(null);
  const [iniciandoVisita, setIniciandoVisita] = useState(false);
  const [finalizandoVisita, setFinalizandoVisita] = useState(false);
  const [erroVisita, setErroVisita] = useState("");

  const [visitas, setVisitas] = useState(null);

  const [historico, setHistorico] = useState(null);
  const [pagina, setPagina] = useState(1);
  const [carregandoHist, setCarregandoHist] = useState(false);
  const [ordenarCampo, setOrdenarCampo] = useState("valorTotal");
  const [ordenarAsc, setOrdenarAsc] = useState(false);

  const [vinculo, setVinculo] = useState(null);
  const [buscaVinculo, setBuscaVinculo] = useState("");
  const [resultadosVinculo, setResultadosVinculo] = useState(null);
  const [vinculando, setVinculando] = useState(false);
  const [erroVinculo, setErroVinculo] = useState("");

  function formatarData(iso) {
    if (!iso) return "—";
    return new Date(iso).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric" });
  }

  // Uma requisição só traz cliente, promessas, visitas, histórico e vínculo.
  // Antes eram 4-5 chamadas ao abrir a ficha, duas delas em série (o vínculo
  // esperava o cliente chegar). A ~350ms de ida e volta cada, a ficha levava
  // segundos para montar no celular em campo.
  useEffect(() => {
    let vivo = true;
    setCarregandoHist(true);
    setPagina(1);
    api.get(`/api/clientes/${cliente.id}/ficha`)
      .then((ficha) => {
        if (!vivo) return;
        setPromessas(ficha.promessas);
        setVisitas(ficha.visitas);
        setHistorico(ficha.historico);
        setVinculo(ficha.vinculo);
        // o cliente vem fresco do banco em vez de confiar só na prop: um
        // vínculo pode ter sido criado/desfeito em outra tela (ex.: revisão de
        // sugestões) sem que a lista principal do app tenha sido atualizada.
        if (ehAdmin && ficha.cliente.clienteMestreId !== cliente.clienteMestreId) {
          aoAtualizar(ficha.cliente);
        }
      })
      .catch(() => {
        if (!vivo) return;
        setPromessas([]);
        setVisitas([]);
        setHistorico({ total: 0, itens: [] });
        setVinculo(null);
      })
      .finally(() => { if (vivo) setCarregandoHist(false); });
    return () => { vivo = false; };
  }, [cliente.id, ehAdmin]);

  async function buscarParaVincular(e) {
    e.preventDefault();
    if (buscaVinculo.trim().length < 2) return;
    try {
      const r = await api.get(`/api/vinculos/buscar?q=${encodeURIComponent(buscaVinculo)}&excluirId=${cliente.id}`);
      setResultadosVinculo(r);
    } catch (err) {
      setErroVinculo(err.message);
    }
  }

  async function vincularCom(outroId) {
    setVinculando(true);
    setErroVinculo("");
    try {
      const consolidado = await api.post("/api/vinculos", { clienteIds: [cliente.id, outroId] });
      setVinculo(consolidado);
      setResultadosVinculo(null);
      setBuscaVinculo("");
      const atualizado = await api.get(`/api/clientes/${cliente.id}`);
      aoAtualizar(atualizado);
    } catch (err) {
      setErroVinculo(err.message);
    } finally {
      setVinculando(false);
    }
  }

  async function desvincularMembro(membroId) {
    if (!vinculo) return;
    try {
      await api.del(`/api/vinculos/${vinculo.id}/membros/${membroId}`);
      if (membroId === cliente.id) {
        setVinculo(null);
        const atualizado = await api.get(`/api/clientes/${cliente.id}`);
        aoAtualizar(atualizado);
      } else {
        const consolidado = await api.get(`/api/vinculos/${vinculo.id}`).catch(() => null);
        setVinculo(consolidado);
      }
    } catch (err) {
      setErroVinculo(err.message);
    }
  }

  async function cumprirPromessa(id) {
    await api.patch(`/api/visitas/promessas/${id}/cumprir`, {});
    setPromessas((lista) => lista.filter((p) => p.id !== id));
  }

  async function finalizarVisita() {
    setFinalizandoVisita(true);
    setErroVisita("");
    try {
      await aoFinalizarVisita();
      aoFechar(); // o modal bloqueante de relatório assume a tela por cima
    } catch (err) {
      setErroVisita(err.message);
    } finally {
      setFinalizandoVisita(false);
    }
  }

  async function iniciarVisita() {
    setIniciandoVisita(true);
    setErroVisita("");
    try {
      await aoIniciarVisita(cliente.id);
      aoFechar();
    } catch (err) {
      setErroVisita(err.message);
    } finally {
      setIniciandoVisita(false);
    }
  }

  const temVisitaEmOutroCliente = visitaPendente && visitaPendente.clienteId !== cliente.id;
  const temVisitaNesteCliente = visitaPendente && visitaPendente.clienteId === cliente.id;

  function ordenarPor(coluna) {
    if (ordenarCampo === coluna.campo) {
      setOrdenarAsc((a) => !a);
    } else {
      setOrdenarCampo(coluna.campo);
      setOrdenarAsc(coluna.ascPadrao);
    }
    setPagina(1);
  }

  const itensOrdenados = useMemo(() => {
    if (!historico) return [];
    const coluna = COLUNAS_HISTORICO.find((c) => c.campo === ordenarCampo);
    const itens = [...historico.itens];
    itens.sort((a, b) => {
      const va = a[ordenarCampo], vb = b[ordenarCampo];
      let cmp;
      if (coluna.tipo === "texto") cmp = (va || "").localeCompare(vb || "");
      else if (coluna.tipo === "data") cmp = (va || "") < (vb || "") ? -1 : (va || "") > (vb || "") ? 1 : 0;
      else cmp = (va || 0) - (vb || 0);
      return ordenarAsc ? cmp : -cmp;
    });
    return itens;
  }, [historico, ordenarCampo, ordenarAsc]);

  async function salvarContato(e) {
    e.preventDefault();
    setSalvandoContato(true);
    setErroContato("");
    try {
      const atualizado = await api.patch(`/api/clientes/${cliente.id}`, { contatoNome, contatoCelular });
      aoAtualizar(atualizado);
    } catch (err) {
      setErroContato(err.message);
    } finally {
      setSalvandoContato(false);
    }
  }

  async function salvarStatus() {
    setSalvandoStatus(true);
    setErroStatus("");
    try {
      const corpo = { status, aceitaVisita, motivoRecusaVisita: aceitaVisita ? null : motivo };
      const atualizado = await api.patch(`/api/clientes/${cliente.id}`, corpo);
      aoAtualizar(atualizado);
    } catch (err) {
      setErroStatus(err.message);
    } finally {
      setSalvandoStatus(false);
    }
  }

  function copiarEndereco() {
    const texto = [cliente.endereco, cliente.bairro, `${cliente.cidade}/${cliente.uf}`]
      .filter(Boolean).join(", ");
    navigator.clipboard.writeText(texto).then(() => {
      setCopiado(true);
      setTimeout(() => setCopiado(false), 1800);
    });
  }

  const totalPaginas = Math.max(1, Math.ceil(itensOrdenados.length / TAMANHO_PAGINA));
  const itensPagina = itensOrdenados.slice((pagina - 1) * TAMANHO_PAGINA, pagina * TAMANHO_PAGINA);

  return (
    <div className="modal-fundo" onClick={aoFechar}>
      <div className="modal-ficha" onClick={(e) => e.stopPropagation()}>
        <button className="modal-fechar" onClick={aoFechar} aria-label="Fechar">×</button>

        <div className="ficha-header">
          <span className={"chip " + FAIXA_CHIP[cliente.faixa]}>
            <span className={"dot " + FAIXA_DOT[cliente.faixa]} /> {cliente.faixa || "Sem faixa"}
          </span>
          {cliente.emRisco && <span className="chip chip-risk"><span className="dot dot-risk" /> Em risco</span>}
          {status === "inativo" && <span className="chip chip-inativo">Inativo</span>}
          {!aceitaVisita && status !== "inativo" && (
            <span className="chip chip-motivo">{motivo === "calote" ? "Calote" : "Sem visita"}</span>
          )}
          <h2>{cliente.nome}</h2>
          <p className="muted" style={{ fontSize: 13 }}>
            CNPJ: {cliente.cnpj || "não informado"} {cliente.cnae ? `· ${cliente.cnae}` : ""}
          </p>

          {promessas && promessas.length > 0 && (
            <div className="promessas-pendentes">
              {promessas.map((p) => (
                <div key={p.id} className="promessa-item">
                  <span>🔸 {p.texto}</span>
                  <button className="btn btn-ghost" onClick={() => cumprirPromessa(p.id)}>Cumprida</button>
                </div>
              ))}
            </div>
          )}

          <div style={{ marginTop: 14 }}>
            {temVisitaNesteCliente ? (
              <button className="btn btn-primary" onClick={finalizarVisita} disabled={finalizandoVisita}>
                {finalizandoVisita ? "Finalizando…" : "Finalizar visita"}
              </button>
            ) : !aceitaVisita ? (
              <p className="muted" style={{ fontSize: 13 }}>Este cliente não aceita visita presencial.</p>
            ) : (
              <button
                className="btn btn-primary"
                onClick={iniciarVisita}
                disabled={iniciandoVisita || temVisitaEmOutroCliente}
                title={temVisitaEmOutroCliente ? "Finalize a visita em andamento antes de iniciar outra" : undefined}
              >
                {iniciandoVisita ? "Iniciando…" : "Iniciar visita"}
              </button>
            )}
            {erroVisita && <div className="login-erro" style={{ marginTop: 8 }}>{erroVisita}</div>}
          </div>
        </div>

        <div className="ficha-secao">
          <span className="filtro-titulo">Endereço</span>
          <div className="ficha-endereco">
            <p>
              {cliente.endereco || "endereço não informado"}{cliente.bairro ? `, ${cliente.bairro}` : ""}<br />
              {cliente.cidade}/{cliente.uf}
            </p>
            <button type="button" className="btn btn-ghost" onClick={copiarEndereco}>
              {copiado ? "Copiado!" : "Copiar endereço"}
            </button>
          </div>
        </div>

        <div className="ficha-secao">
          <span className="filtro-titulo">Contato responsável</span>
          <form className="ficha-contato" onSubmit={salvarContato}>
            <input
              className="input" placeholder="Nome do contato"
              value={contatoNome} onChange={(e) => setContatoNome(e.target.value)}
            />
            <input
              className="input" placeholder="Celular"
              value={contatoCelular} onChange={(e) => setContatoCelular(e.target.value)}
            />
            <button className="btn btn-primary" type="submit" disabled={salvandoContato}>
              {salvandoContato ? "Salvando…" : "Salvar contato"}
            </button>
          </form>
          {erroContato && <div className="login-erro" style={{ marginTop: 8 }}>{erroContato}</div>}
          {cliente.telefone && (
            <p className="muted" style={{ fontSize: 12, marginTop: 6 }}>
              Telefone cadastral (Receita): {telefoneFmt(cliente.telefone)}
            </p>
          )}
        </div>

        <div className="kv" style={{ marginTop: 4 }}>
          <div><span>Faturamento</span><b>{brl(cliente.fat)}</b></div>
          <div><span>Compras</span><b>{num(cliente.compras)}</b></div>
          <div><span>Ticket médio</span><b>{brl(cliente.ticket)}</b></div>
          <div><span>Última compra</span><b>{recenciaTexto(cliente.recencia)}</b></div>
          {cliente.porte && <div><span>Porte</span><b>{cliente.porte}</b></div>}
          {cliente.score != null && (
            <div><span>Score RFM</span><b>{cliente.score} <small className="faint">(R{cliente.R} F{cliente.F} M{cliente.M})</small></b></div>
          )}
        </div>

        <div className="ficha-secao">
          <span className="filtro-titulo">Status do cliente</span>
          <div className="ficha-status">
            <label className="ficha-radio">
              <input type="radio" checked={status === "ativo"} onChange={() => setStatus("ativo")} /> Ativo
            </label>
            <label className="ficha-radio">
              <input type="radio" checked={status === "inativo"} onChange={() => setStatus("inativo")} /> Inativo (empresa fechou)
            </label>
          </div>
          <div className="ficha-status" style={{ marginTop: 8 }}>
            <label className="ficha-radio">
              <input type="radio" checked={aceitaVisita} onChange={() => setAceitaVisita(true)} /> Aceita visita
            </label>
            <label className="ficha-radio">
              <input type="radio" checked={!aceitaVisita} onChange={() => setAceitaVisita(false)} /> Não aceita visita
            </label>
          </div>
          {!aceitaVisita && (
            <select className="input" value={motivo} onChange={(e) => setMotivo(e.target.value)} style={{ marginTop: 8, maxWidth: 220 }}>
              <option value="calote">Calote — ainda compra à vista</option>
              <option value="sem-visita">Sem visita — compra por telefone</option>
            </select>
          )}
          <button className="btn btn-ghost" style={{ marginTop: 10 }} onClick={salvarStatus} disabled={salvandoStatus}>
            {salvandoStatus ? "Salvando…" : "Salvar status"}
          </button>
          {erroStatus && <div className="login-erro" style={{ marginTop: 8 }}>{erroStatus}</div>}
        </div>

        <div className="ficha-secao">
          <span className="filtro-titulo">
            Histórico de visitas {visitas ? `(${visitas.length})` : ""}
          </span>
          {!visitas ? (
            <p className="muted" style={{ fontSize: 13 }}>Carregando…</p>
          ) : visitas.length === 0 ? (
            <p className="muted" style={{ fontSize: 13 }}>Nenhuma visita registrada ainda.</p>
          ) : (
            visitas.map((v) => (
              <div key={v.id} className="visita-historico-item">
                <div className="visita-historico-data">{formatarData(v.inicio)}</div>
                <div>{v.observacao}</div>
                {v.retornoData && <div className="visita-historico-promessas">Retorno combinado: {formatarData(v.retornoData)}</div>}
                {v.promessas.length > 0 && (
                  <div className="visita-historico-promessas">
                    Promessas: {v.promessas.map((p) => p.texto + (p.cumprida ? " (cumprida)" : "")).join("; ")}
                  </div>
                )}
              </div>
            ))
          )}
        </div>

        {ehAdmin && (
          <div className="ficha-secao">
            <span className="filtro-titulo">Vínculo de CNPJ</span>
            {vinculo ? (
              <>
                <p className="muted" style={{ fontSize: 13 }}>
                  Agrupado com mais {vinculo.membros.length - 1} CNPJ(s) · faturamento consolidado {brl(vinculo.fatTotal)}
                </p>
                <ul className="vinculo-membros">
                  {vinculo.membros.map((m) => (
                    <li key={m.id}>
                      <span>{m.nome} {m.id === cliente.id && <b>(este)</b>}</span>
                      <button className="btn btn-ghost" onClick={() => desvincularMembro(m.id)}>Desvincular</button>
                    </li>
                  ))}
                </ul>
              </>
            ) : (
              <>
                <form className="ficha-contato" onSubmit={buscarParaVincular}>
                  <input
                    className="input" placeholder="Buscar por nome ou CNPJ para vincular"
                    value={buscaVinculo} onChange={(e) => setBuscaVinculo(e.target.value)}
                  />
                  <button className="btn btn-ghost" type="submit">Buscar</button>
                </form>
                {resultadosVinculo && (
                  resultadosVinculo.length === 0 ? (
                    <p className="muted" style={{ fontSize: 13 }}>Nenhum cliente encontrado.</p>
                  ) : (
                    <ul className="vinculo-membros">
                      {resultadosVinculo.map((r) => (
                        <li key={r.id}>
                          <span>{r.nome} · {r.cidade}</span>
                          <button className="btn btn-ghost" disabled={vinculando} onClick={() => vincularCom(r.id)}>Vincular</button>
                        </li>
                      ))}
                    </ul>
                  )
                )}
              </>
            )}
            {erroVinculo && <div className="login-erro" style={{ marginTop: 8 }}>{erroVinculo}</div>}
          </div>
        )}

        <div className="ficha-secao">
          <span className="filtro-titulo">
            Histórico de compra por item {historico ? `(${num(itensOrdenados.length)})` : ""}
          </span>
          {carregandoHist ? (
            <p className="muted" style={{ fontSize: 13 }}>Carregando…</p>
          ) : !historico || itensOrdenados.length === 0 ? (
            <p className="muted" style={{ fontSize: 13 }}>Sem histórico de compra por item disponível.</p>
          ) : (
            <>
              <div className="tabela-scroll">
                <table className="ficha-tabela-itens">
                  <thead>
                    <tr>
                      {COLUNAS_HISTORICO.map((c) => (
                        <th key={c.campo} className="ordenavel" onClick={() => ordenarPor(c)}>
                          {c.rotulo} {ordenarCampo === c.campo ? (ordenarAsc ? "▲" : "▼") : ""}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {itensPagina.map((it) => (
                      <tr key={it.codigoProduto}>
                        <td>{it.descricaoProduto}</td>
                        <td>{num(it.quantidadeTotal)}</td>
                        <td>{it.numeroCompras}</td>
                        <td>{it.ultimaCompra || "—"}</td>
                        <td>{brl(it.valorTotal)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {totalPaginas > 1 && (
                <div className="ficha-paginacao">
                  <button className="btn btn-ghost" disabled={pagina <= 1} onClick={() => setPagina((p) => p - 1)}>‹ Anterior</button>
                  <span className="muted" style={{ fontSize: 13 }}>Página {pagina} de {totalPaginas}</span>
                  <button className="btn btn-ghost" disabled={pagina >= totalPaginas} onClick={() => setPagina((p) => p + 1)}>Próxima ›</button>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

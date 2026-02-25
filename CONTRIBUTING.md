# Guia de Contribuição para MangaNexus

Bem-vindo(a) ao projeto MangaNexus! Agradecemos o seu interesse em contribuir. Para garantir um processo de colaboração eficiente e agradável para todos, por favor, siga estas diretrizes.

## Como Contribuir

Existem diversas formas de contribuir para o MangaNexus:

*   **Reportar Bugs:** Se você encontrar um erro ou comportamento inesperado, por favor, abra uma issue.
*   **Sugerir Melhorias:** Tem uma ideia para uma nova funcionalidade ou uma forma de melhorar algo existente? Abra uma issue para discutir.
*   **Escrever Código:** Contribua com novas funcionalidades, correções de bugs ou melhorias de código.
*   **Melhorar a Documentação:** Ajude a tornar a documentação mais clara e completa.

## Reportando Bugs e Sugerindo Melhorias

Antes de abrir uma nova issue, por favor, verifique se já existe uma issue semelhante. Se não houver, siga estas etapas:

1.  Clique em "New issue" na aba [Issues](https://github.com/seu-usuario/manganexus/issues) do repositório.
2.  Escolha o modelo apropriado (Bug Report ou Feature Request).
3.  Preencha todos os campos solicitados com o máximo de detalhes possível.
    *   **Para Bugs:** Inclua passos para reproduzir, comportamento esperado, comportamento atual e informações do seu ambiente (navegador, sistema operacional, etc.).
    *   **Para Sugestões:** Descreva a funcionalidade, o problema que ela resolve e como você imagina que ela funcionaria.

## Contribuindo com Código

Para contribuir com código, siga o fluxo de trabalho padrão do GitHub:

1.  **Faça um Fork** do repositório para a sua conta GitHub.
2.  **Clone o seu Fork** para a sua máquina local:
    ```bash
    git clone https://github.com/seu-usuario/manganexus.git
    cd manganexus
    ```
3.  **Crie um Novo Branch** para a sua contribuição. Use um nome descritivo (ex: `feature/nova-funcionalidade` ou `fix/bug-de-login`):
    ```bash
    git checkout -b feature/minha-feature
    ```
4.  **Faça suas Alterações** no código.
5.  **Commit suas Alterações** com mensagens claras e concisas. Use o [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) se possível (ex: `feat: adiciona nova funcionalidade`, `fix: corrige bug de autenticação`).
    ```bash
    git commit -m 'feat: adiciona minha feature'
    ```
6.  **Envie suas Alterações** para o seu fork no GitHub:
    ```bash
    git push origin feature/minha-feature
    ```
7.  **Abra um Pull Request (PR)** para o repositório original do MangaNexus. Certifique-se de:
    *   Descrever claramente as mudanças e o problema que elas resolvem.
    *   Referenciar qualquer issue relacionada (ex: `Closes #123`).
    *   Garantir que todos os testes (se houver) passem.

## Padrões de Código

*   **Python (Backend):** Siga o estilo de código [PEP 8](https://www.python.org/dev/peps/pep-0008/).
*   **HTML/CSS/JavaScript (Frontend):** Mantenha o código limpo, legível e bem comentado. Priorize a simplicidade e o desempenho.

## Processo de Revisão de Pull Request

Todos os Pull Requests serão revisados pelos mantenedores do projeto. O feedback será fornecido o mais rápido possível. Por favor, seja paciente e esteja aberto(a) a sugestões e discussões. Seu PR será mesclado assim que as alterações forem aprovadas e passarem por quaisquer verificações automatizadas.

## Licença

Ao contribuir para o MangaNexus, você concorda que suas contribuições serão licenciadas sob a licença MIT do projeto. Veja o arquivo `LICENSE` para mais detalhes.

Obrigado por fazer parte do MangaNexus!

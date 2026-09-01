import type {SidebarsConfig} from '@docusaurus/plugin-content-docs';

const sidebars: SidebarsConfig = {
  docsSidebar: [
    'INDEX',
    {
      type: 'category',
      label: 'Core',
      items: [
        'overview',
        'architecture',
        'conventions',
        'deployment',
        'data-model',
      ],
    },
    {
      type: 'category',
      label: 'EVA service reference',
      items: [
        'references/generator',
        'references/cli',
        'references/service-catalog',
        'references/api-reference',
        'references/identity',
        'references/ai-knowledge-agents',
        'references/platform-services',
        'references/production-readiness',
        'references/documentation-reliability',
      ],
    },
  ],
};

export default sidebars;

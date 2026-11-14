import { CatalogService } from './catalog.service';
import { ChatStateService } from './chat-state.service';
import { IPublicPersona, PersonaValues } from '../data/models/catalog.model';

describe('The default agent of a new conversation', () => {
  const assistant: IPublicPersona = { id: 7, name: 'Assistant', systemPrompt: 'Help', variables: [] };
  const pirate: IPublicPersona = { id: 8, name: 'Pirate', systemPrompt: 'Arr', variables: [] };
  // Private static of ChatStateService: a draft's selection with the default agent
  const withDefault = (draft: { modelId: number | null; personaId: number | null | undefined;
                                personaValues: PersonaValues | null }, defaultId: number | null) =>
    (ChatStateService as any)['withDefaultPersona'](draft, defaultId);

  it('is offered only while it is in the list (the catalog, without hidden ones in family mode)', () => {
    expect(CatalogService.defaultPersona(7, [assistant, pirate])).toBe(assistant);
    expect(CatalogService.defaultPersona(9, [assistant, pirate])).toBeNull();
    expect(CatalogService.defaultPersona(null, [assistant])).toBeNull();
    expect(CatalogService.defaultPersona(undefined, [assistant])).toBeNull();
  });

  it('starts a draft without a picked agent, and keeps a picked one or none', () => {
    expect(withDefault({ modelId: 3, personaId: undefined, personaValues: null }, 7))
      .toEqual({ modelId: 3, personaId: 7, personaValues: null });
    expect(withDefault({ modelId: null, personaId: null, personaValues: null }, 7))
      .toEqual({ modelId: null, personaId: null, personaValues: null });
    expect(withDefault({ modelId: null, personaId: 8, personaValues: { style: 'poet' } }, 7))
      .toEqual({ modelId: null, personaId: 8, personaValues: { style: 'poet' } });
    expect(withDefault({ modelId: null, personaId: undefined, personaValues: null }, null))
      .toEqual({ modelId: null, personaId: null, personaValues: null });
  });
});

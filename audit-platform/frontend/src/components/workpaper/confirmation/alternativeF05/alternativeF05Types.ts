import type { AlternativeCompany } from '../alternativeD05/alternativeD05Types'

export interface AlternativeF05Payload {
  _format: 'alternative-f05-v1'
  companies: AlternativeCompany[]
}

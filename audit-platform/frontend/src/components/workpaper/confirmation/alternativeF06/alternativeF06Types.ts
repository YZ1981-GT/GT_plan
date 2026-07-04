import type { AlternativeCompany } from '../alternativeD05/alternativeD05Types'

export interface AlternativeF06Payload {
  _format: 'alternative-f06-v1'
  companies: AlternativeCompany[]
}

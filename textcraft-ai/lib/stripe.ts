import Stripe from 'stripe';

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!, {
  apiVersion: '2024-12-18.acacia',
  typescript: true,
});

export default stripe;

export const STRIPE_PRO_PRICE_ID = process.env.STRIPE_PRO_PRICE_ID!;

module.exports = {
  root: true,
  env: {
    browser: true,
    es2022: true,
  },
  parserOptions: {
    ecmaVersion: "latest",
    sourceType: "script",
  },
  globals: {
    Office: "readonly",
    Excel: "readonly",
    CONFIG: "readonly",
  },
  overrides: [
    {
      files: ["tests/**/*.js"],
      env: {
        node: true,
        browser: false,
      },
    },
  ],
  rules: {
    "no-undef": "error",
    "no-unreachable": "error",
  },
};

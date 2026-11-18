/* MultiMotor_N6 — FSBL application (runs from SRAM @0x34180400 on NUCLEO-N657X0-Q)
 *
 * Bring-up firmware: ST's N6 template clock tree + LEDs + VCP console.
 *   Console : USART1 PE5(TX)/PE6(RX) -> ST-LINK VCP, 115200 8N1
 *   LEDs    : LD6 green PG0, LD7 blue PG8, LD5 red PG10 (all ACTIVE LOW)
 * Protocol  : line-based, same family as the C092 build (see ../../MultiMotor).
 */
#include "main.h"
#include <string.h>

void SystemClock_Config(void);
void Error_Handler(void);

#define LED_G GPIO_PIN_0   /* PG0  green  */
#define LED_B GPIO_PIN_8   /* PG8  blue   */
#define LED_R GPIO_PIN_10  /* PG10 red    */

static UART_HandleTypeDef huart1;
static volatile uint32_t ticks_ms;

static void LED_Init(void)
{
  GPIO_InitTypeDef g = {0};
  __HAL_RCC_GPIOG_CLK_ENABLE();
  g.Pin   = LED_R | LED_G | LED_B;
  g.Mode  = GPIO_MODE_OUTPUT_PP;
  g.Pull  = GPIO_NOPULL;
  g.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(GPIOG, &g);
  HAL_GPIO_WritePin(GPIOG, LED_R | LED_G | LED_B, GPIO_PIN_SET); /* off */
}
static void LED(uint32_t pin, int on) { HAL_GPIO_WritePin(GPIOG, pin, on ? GPIO_PIN_RESET : GPIO_PIN_SET); }

static void UART1_Init(void)
{
  GPIO_InitTypeDef g = {0};
  __HAL_RCC_USART1_CLK_ENABLE();
  __HAL_RCC_GPIOE_CLK_ENABLE();
  __HAL_RCC_USART1_CONFIG(RCC_USART1CLKSOURCE_PCLK2);

  g.Pin       = GPIO_PIN_5 | GPIO_PIN_6;      /* PE5 TX, PE6 RX (ST-LINK VCP) */
  g.Mode      = GPIO_MODE_AF_PP;
  g.Pull      = GPIO_PULLUP;
  g.Speed     = GPIO_SPEED_FREQ_VERY_HIGH;
  g.Alternate = GPIO_AF7_USART1;
  HAL_GPIO_Init(GPIOE, &g);

  memset(&huart1, 0, sizeof huart1);
  huart1.Instance          = USART1;
  huart1.Init.BaudRate     = 115200;
  huart1.Init.WordLength   = UART_WORDLENGTH_8B;
  huart1.Init.StopBits     = UART_STOPBITS_1;
  huart1.Init.Parity       = UART_PARITY_NONE;
  huart1.Init.Mode         = UART_MODE_TX_RX;
  huart1.Init.HwFlowCtl    = UART_HWCONTROL_NONE;
  huart1.Init.OverSampling = UART_OVERSAMPLING_16;
  if (HAL_UART_Init(&huart1) != HAL_OK) Error_Handler();
}
static void TX(const char *s)
{
  HAL_UART_Transmit(&huart1, (uint8_t *)s, (uint16_t)strlen(s), 200);
}

int main(void)
{
  SCB_EnableICache();
  SCB_EnableDCache();
  HAL_Init();
  SystemClock_Config();

  LED_Init();
  UART1_Init();

  TX("\r\n# NUCLEO-N657X0-Q MultiMotor_N6 bring-up\r\n");
  TX("# console: USART1 VCP @115200 | LEDs: PG0/PG8/PG10 (act-low)\r\n");
  TX("# type anything: A=arm n/a, D=disarm, P=probe ping\r\n");

  uint32_t last_beat = HAL_GetTick();
  uint8_t  c;
  while (1) {
    /* heartbeat: green LED blink + status line */
    if ((HAL_GetTick() - last_beat) >= 1000) {
      last_beat = HAL_GetTick();
      ticks_ms  = HAL_GetTick();
      LED(LED_G, 1); HAL_Delay(30); LED(LED_G, 0);
      TX("N6 alive ");
      char buf[32]; uint32_t t = ticks_ms;
      int i = 0; buf[i++] = ' '; buf[i++] = 't';
      buf[i++] = '='; 
      char n[12]; int k = 0; do { n[k++] = '0' + (t % 10); t /= 10; } while (t);
      while (k) buf[i++] = n[--k];
      buf[i++] = '\r'; buf[i++] = '\n'; buf[i] = 0;
      TX(buf);
    }

    /* console echo with commands */
    if (HAL_UART_Receive(&huart1, &c, 1, 5) == HAL_OK) {
      if (c == 'A')      { TX("ARMED\r\n"); LED(LED_B, 1); }
      else if (c == 'D') { TX("DISARMED\r\n"); LED(LED_B, 0); LED(LED_R, 0); }
      else if (c == 'P') { TX("PONG N657 id=0x486\r\n"); }
      else if (c == '\r' || c == '\n') { TX("\r\n"); }
      else { HAL_UART_Transmit(&huart1, &c, 1, 50); }
    }
  }
}

/* ── System Clock: identical to ST's N6 template (600 MHz from PLL1/HSI) ── */
void SystemClock_Config(void)
{
  RCC_OscInitTypeDef   RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef   RCC_ClkInitStruct = {0};

  if (HAL_PWREx_ConfigSupply(PWR_EXTERNAL_SOURCE_SUPPLY) != HAL_OK) Error_Handler();
  if (HAL_PWREx_ControlVoltageScaling(PWR_REGULATOR_VOLTAGE_SCALE1) != HAL_OK) Error_Handler();

  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSI;
  RCC_OscInitStruct.HSIState       = RCC_HSI_ON;
  RCC_OscInitStruct.HSIDiv         = RCC_HSI_DIV1;
  RCC_OscInitStruct.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
  RCC_OscInitStruct.PLL1.PLLState  = RCC_PLL_NONE;
  RCC_OscInitStruct.PLL2.PLLState  = RCC_PLL_NONE;
  RCC_OscInitStruct.PLL3.PLLState  = RCC_PLL_NONE;
  RCC_OscInitStruct.PLL4.PLLState  = RCC_PLL_NONE;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK) Error_Handler();

  HAL_RCC_GetClockConfig(&RCC_ClkInitStruct);
  if ((RCC_ClkInitStruct.CPUCLKSource == RCC_CPUCLKSOURCE_IC1) ||
      (RCC_ClkInitStruct.SYSCLKSource == RCC_SYSCLKSOURCE_IC2_IC6_IC11)) {
    RCC_ClkInitStruct.ClockType  = (RCC_CLOCKTYPE_CPUCLK | RCC_CLOCKTYPE_SYSCLK);
    RCC_ClkInitStruct.CPUCLKSource = RCC_CPUCLKSOURCE_HSI;
    RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_HSI;
    if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct) != HAL_OK) Error_Handler();
  }

  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_NONE;
  RCC_OscInitStruct.PLL1.PLLState     = RCC_PLL_ON;
  RCC_OscInitStruct.PLL1.PLLSource    = RCC_PLLSOURCE_HSI;
  RCC_OscInitStruct.PLL1.PLLM         = 4;
  RCC_OscInitStruct.PLL1.PLLN         = 75;
  RCC_OscInitStruct.PLL1.PLLFractional = 0;
  RCC_OscInitStruct.PLL1.PLLP1        = 1;
  RCC_OscInitStruct.PLL1.PLLP2        = 1;
  RCC_OscInitStruct.PLL2.PLLState     = RCC_PLL_NONE;
  RCC_OscInitStruct.PLL3.PLLState     = RCC_PLL_NONE;
  RCC_OscInitStruct.PLL4.PLLState     = RCC_PLL_NONE;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK) Error_Handler();

  RCC_ClkInitStruct.ClockType     = RCC_CLOCKTYPE_CPUCLK|RCC_CLOCKTYPE_HCLK
                                  |RCC_CLOCKTYPE_SYSCLK|RCC_CLOCKTYPE_PCLK1
                                  |RCC_CLOCKTYPE_PCLK2|RCC_CLOCKTYPE_PCLK5
                                  |RCC_CLOCKTYPE_PCLK4;
  RCC_ClkInitStruct.CPUCLKSource  = RCC_CPUCLKSOURCE_IC1;
  RCC_ClkInitStruct.SYSCLKSource  = RCC_SYSCLKSOURCE_IC2_IC6_IC11;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_HCLK_DIV2;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_APB1_DIV1;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_APB2_DIV1;
  RCC_ClkInitStruct.APB4CLKDivider = RCC_APB4_DIV1;
  RCC_ClkInitStruct.APB5CLKDivider = RCC_APB5_DIV1;
  RCC_ClkInitStruct.IC1Selection.ClockSelection  = RCC_ICCLKSOURCE_PLL1;
  RCC_ClkInitStruct.IC1Selection.ClockDivider   = 2;
  RCC_ClkInitStruct.IC2Selection.ClockSelection  = RCC_ICCLKSOURCE_PLL1;
  RCC_ClkInitStruct.IC2Selection.ClockDivider   = 3;
  RCC_ClkInitStruct.IC6Selection.ClockSelection  = RCC_ICCLKSOURCE_PLL1;
  RCC_ClkInitStruct.IC6Selection.ClockDivider   = 4;
  RCC_ClkInitStruct.IC11Selection.ClockSelection = RCC_ICCLKSOURCE_PLL1;
  RCC_ClkInitStruct.IC11Selection.ClockDivider  = 3;
  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct) != HAL_OK) Error_Handler();
}

void Error_Handler(void)
{
  __disable_irq();
  for (;;) { if (LED_R) { } }   /* red LED stays on if we get here */
}

#ifdef USE_FULL_ASSERT
void assert_failed(uint8_t *file, uint32_t line)
{
  (void)file; (void)line;
}
#endif

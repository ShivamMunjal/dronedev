/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file    stm32c0xx_it.c
  * @brief   Interrupt Service Routines — SysTick, EXTI (button), USART2
  ******************************************************************************
  */
/* USER CODE END Header */

#include "main.h"
#include "stm32c0xx_it.h"

/* External variables */
extern UART_HandleTypeDef huart2;

/******************************************************************************/
/*           Cortex Processor Interruption and Exception Handlers             */
/******************************************************************************/

void NMI_Handler(void)
{
    while (1) {}
}

void HardFault_Handler(void)
{
    while (1) {}
}

void SVC_Handler(void)
{
}

void PendSV_Handler(void)
{
}

void SysTick_Handler(void)
{
    HAL_IncTick();
}

/******************************************************************************/
/*           STM32C0xx Peripheral Interrupt Handlers                          */
/******************************************************************************/

/**
  * @brief EXTI line 4-15 — User button (PC13) kill switch
  */
void EXTI4_15_IRQHandler(void)
{
    BSP_PB_IRQHandler(BUTTON_USER);
}

/**
  * @brief USART2 global interrupt — UART RX
  */
void USART2_IRQHandler(void)
{
    HAL_UART_IRQHandler(&huart2);
}
